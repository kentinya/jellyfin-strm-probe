using System.Globalization;
using Jellyfin.Plugin.StrmProbeOptimizer.Interceptors;
using Jellyfin.Database.Implementations.Entities;
using Jellyfin.Data.Enums;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Library;
using MediaBrowser.Model.Dto;
using MediaBrowser.Model.Entities;
using Microsoft.Extensions.Logging;

namespace Jellyfin.Plugin.StrmProbeOptimizer.Services;

public sealed class StrmPlaybackOptimizer
{
    private readonly IStrmManifestReader _manifestReader;
    private readonly IProbeDecisionService _decisionService;
    private readonly IStrmFingerprintRepository _fingerprintRepository;
    private readonly IPlaybackSettings _settings;
    private readonly ILogger<StrmPlaybackOptimizer> _logger;
    private readonly ILibraryManager? _libraryManager;
    private readonly Lazy<ProbeCoordinator> _coordinator;
    private int _fingerprintStoreFailed;

    public StrmPlaybackOptimizer(
        IStrmManifestReader manifestReader,
        IProbeDecisionService decisionService,
        IStrmFingerprintRepository fingerprintRepository,
        IPlaybackSettings settings,
        ILogger<StrmPlaybackOptimizer> logger,
        ILibraryManager? libraryManager = null,
        ProbeCoordinator? coordinator = null)
    {
        _manifestReader = manifestReader;
        _decisionService = decisionService;
        _fingerprintRepository = fingerprintRepository;
        _settings = settings;
        _logger = logger;
        _libraryManager = libraryManager;
        // Jellyfin resolves IMediaSourceManager (and therefore this optimizer) before it creates plugin
        // instances, so the global pool must be created on first use. It then reads the concurrency that was
        // captured when the plugin started, so a saved change still only applies after the next restart.
        _coordinator = new Lazy<ProbeCoordinator>(() =>
        {
            var pool = coordinator ?? new ProbeCoordinator(settings.MaxConcurrentProbes);
            logger.LogInformation(
                "STRM Probe Optimizer global probe pool created with {MaxConcurrentProbes} permit(s).",
                pool.MaxConcurrentProbes);
            return pool;
        });
    }

    private ProbeCoordinator Coordinator => _coordinator.Value;

    /// <summary>
    /// Gets or sets a test-only barrier that runs when a caller joins an existing same-source probe. It lets a
    /// deterministic regression wait until the joining caller has actually reached the shared wait instead of
    /// relying on a timing delay. It is <c>null</c> in production.
    /// </summary>
    internal Action? SharedJoinBarrier { get; set; }

    public async Task<IReadOnlyList<MediaSourceInfo>> GetPlaybackMediaSourcesAsync(
        IMediaSourceManager native,
        BaseItem item,
        User? user,
        bool allowMediaProbe,
        bool enablePathSubstitution,
        CancellationToken cancellationToken)
    {
        if (!_settings.Enabled || !_settings.PlaybackAutoCheck || !allowMediaProbe || Volatile.Read(ref _fingerprintStoreFailed) != 0)
        {
            return await DelegateAsync(native, item, user, allowMediaProbe, enablePathSubstitution, cancellationToken)
                .ConfigureAwait(false);
        }

        if (_libraryManager is null
            && (!IsStrm(item) || _manifestReader.Read(item.Path).Status != ManifestReadStatus.Supported))
        {
            return await DelegateAsync(native, item, user, allowMediaProbe, enablePathSubstitution, cancellationToken)
                .ConfigureAwait(false);
        }

        var staticSources = native.GetStaticMediaSources(item, enablePathSubstitution, user);
        var sourceItems = ResolveVisibleSourceItems(item, user, staticSources, out var allSourcesResolved);
        if (!allSourcesResolved)
        {
            _logger.LogWarning("A visible Jellyfin media source could not be mapped to its owning item for {ItemId}; delegating playback without optimization.", item.Id);
            return await DelegateAsync(native, item, user, allowMediaProbe, enablePathSubstitution, cancellationToken)
                .ConfigureAwait(false);
        }

        var supportedSourceCount = FilterSupportedSourceItems(sourceItems, _manifestReader).Count;

        if (supportedSourceCount == 0)
        {
            return await DelegateAsync(native, item, user, allowMediaProbe, enablePathSubstitution, cancellationToken)
                .ConfigureAwait(false);
        }

        var replacements = new Dictionary<string, MediaSourceInfo>(StringComparer.OrdinalIgnoreCase);
        var checkedManifests = new Dictionary<Guid, ManifestReadResult>();
        foreach (var entry in sourceItems)
        {
            var manifestBefore = IsStrm(entry.Item)
                ? _manifestReader.Read(entry.Item.Path)
                : ManifestReadResult.Unsupported;
            var replacement = await CheckSourceAsync(
                native,
                GetProjectId(entry.Item),
                entry.Item,
                entry.Source,
                entry.SourceId.ToString("N", CultureInfo.InvariantCulture),
                allowMediaProbe,
                user,
                enablePathSubstitution,
                cancellationToken,
                isPlaybackContext: true).ConfigureAwait(false);
            if (IsStrm(entry.Item))
            {
                var manifestAfter = _manifestReader.Read(entry.Item.Path);
                if (!SameManifest(manifestBefore, manifestAfter))
                {
                    _logger.LogWarning("STRM manifest changed while source {SourceId} was being checked for item {ItemId}; playback must retry.", entry.SourceId, item.Id);
                    throw new InvalidOperationException("A STRM changed while Jellyfin playback sources were being prepared; playback must retry.");
                }

                checkedManifests[entry.SourceId] = manifestBefore;
            }

            if (replacement is not null)
            {
                replacements[entry.SourceId.ToString("N", CultureInfo.InvariantCulture)] = replacement;
            }
        }

        var currentSources = await DelegateAsync(native, item, user, allowMediaProbe: false, enablePathSubstitution, cancellationToken)
            .ConfigureAwait(false);
        EnsureVisibleSourcesAndManifestsCurrent(item, sourceItems, checkedManifests, currentSources);
        if (replacements.Count == 0)
        {
            return currentSources;
        }

        var result = currentSources.ToArray();
        foreach (var replacement in replacements)
        {
            var index = Array.FindIndex(result, source => HasSourceId(source, replacement.Key));
            if (index < 0)
            {
                _logger.LogWarning("Jellyfin no longer returned visible media source {SourceId} for item {ItemId}; playback response was not rewritten.", replacement.Key, item.Id);
                throw new InvalidOperationException("Jellyfin's visible media source set changed during STRM processing; playback must retry.");
            }

            result[index] = replacement.Value;
        }

        return result;
    }

    /// <summary>
    /// Checks one caller-visible source. This is the shared source-level entry point for playback and a future native task.
    /// It re-reads the current manifest, configuration and fingerprint every time it obtains an execution opportunity, so a
    /// queued caller never starts from a stale decision. A queued or waiting caller is not registered as a running probe.
    /// </summary>
    /// <param name="isPlaybackContext">
    /// <c>true</c> when the caller is the playback entry point. Playback check disablement only applies to this context;
    /// a future shared batch source entry keeps its own admission boundary.
    /// </param>
    public async Task<MediaSourceInfo?> CheckSourceAsync(
        IMediaSourceManager native,
        Guid projectItemId,
        BaseItem sourceItem,
        MediaSourceInfo source,
        string sourceKey,
        bool allowMediaProbe,
        User? user,
        bool enablePathSubstitution,
        CancellationToken cancellationToken,
        bool isPlaybackContext = false)
    {
        var sourceId = source.Id;
        if (!allowMediaProbe)
        {
            return await GetSourceWithNativeAsync(native, sourceItem, sourceId, allowMediaProbe: false, user, enablePathSubstitution, cancellationToken)
                .ConfigureAwait(false);
        }

        if (!CanOptimize(isPlaybackContext))
        {
            return await GetSourceWithNativeAsync(native, sourceItem, sourceId, allowMediaProbe, user, enablePathSubstitution, cancellationToken)
                .ConfigureAwait(false);
        }

        return await CheckSourceCoreAsync(
            native,
            projectItemId,
            sourceItem,
            source,
            sourceKey,
            isPlaybackContext,
            user,
            enablePathSubstitution,
            cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Checks one batch candidate source. It reuses the same manifest reader, decision service, coordinator,
    /// native probe and conditional fingerprint commit as playback, but keeps a batch-specific admission policy:
    /// it never delegates to a native probe, never elevates probe permission, and stops starting new work when the
    /// batch stop or the fingerprint store failure is confirmed. It returns exactly one counted outcome per candidate.
    /// </summary>
    /// <param name="native">The real Jellyfin media source manager.</param>
    /// <param name="projectItemId">The stable project identity (the native primary version id when present).</param>
    /// <param name="sourceItem">The physical candidate item.</param>
    /// <param name="source">The candidate's current native source.</param>
    /// <param name="sourceKey">The stable source key (the candidate item id in N format).</param>
    /// <param name="stopSignal">The batch start/stop boundary for this run.</param>
    /// <returns>The counted batch outcome for this candidate.</returns>
    public async Task<BatchSourceOutcome> CheckBatchSourceAsync(
        IMediaSourceManager native,
        Guid projectItemId,
        BaseItem sourceItem,
        MediaSourceInfo source,
        string sourceKey,
        BatchStopSignal stopSignal,
        IReadOnlyList<Guid>? scopeLibraryIds = null,
        IBatchScopeVerifier? scopeVerifier = null)
    {
        ArgumentNullException.ThrowIfNull(native);
        ArgumentNullException.ThrowIfNull(sourceItem);
        ArgumentNullException.ThrowIfNull(source);
        ArgumentNullException.ThrowIfNull(stopSignal);
        if (IsFingerprintStoreUnavailable)
        {
            throw new FingerprintStoreUnavailableException();
        }

        if (stopSignal.IsStopped)
        {
            return BatchSourceOutcome.Revoked;
        }

        // Re-check the current library relationship at the entry so an object that left the selected scope or
        // changed type is settled as missing instead of being probed from a stale candidate decision.
        if (scopeVerifier is not null && scopeLibraryIds is not null && !scopeVerifier.IsInScope(sourceItem, scopeLibraryIds))
        {
            return BatchSourceOutcome.Missing;
        }

        if (!IsStrm(sourceItem))
        {
            return BatchSourceOutcome.NotProcessed;
        }

        var readResult = _manifestReader.Read(sourceItem.Path);
        if (readResult.Status is ManifestReadStatus.Invalid or ManifestReadStatus.Unavailable)
        {
            return BatchSourceOutcome.CheckStageIncomplete;
        }

        if (readResult.Status != ManifestReadStatus.Supported || readResult.Manifest is not { } manifest)
        {
            return BatchSourceOutcome.NotProcessed;
        }

        StrmFingerprint? previous;
        try
        {
            previous = _fingerprintRepository.Get(projectItemId, sourceKey);
        }
        catch (Exception exception)
        {
            MarkFingerprintStoreFailed(exception, sourceItem.Id);
            throw new FingerprintStoreUnavailableException(exception);
        }

        var decision = _decisionService.Decide(
            manifest,
            previous,
            HasPrimaryStream(sourceItem, source),
            source.Path ?? sourceItem.ShortcutPath);

        BatchDecisionBarrier?.Invoke();

        if (decision.Kind is ProbeDecisionKind.SkipProbe or ProbeDecisionKind.TrustExisting)
        {
            if (!ManifestIsStillCurrent(sourceItem.Path, manifest))
            {
                // The STRM changed while the decision was being made. Never publish a stale baseline; count the
                // candidate as an incomplete check so the next run re-evaluates the current version.
                return BatchSourceOutcome.CheckStageIncomplete;
            }

            if (decision.Kind == ProbeDecisionKind.TrustExisting)
            {
                try
                {
                    if (_fingerprintRepository.TryCommit(CreateFingerprint(projectItemId, sourceKey, manifest), expectedPrevious: null))
                    {
                        return BatchSourceOutcome.FirstTrust;
                    }
                }
                catch (Exception exception)
                {
                    MarkFingerprintStoreFailed(exception, sourceItem.Id);
                    throw new FingerprintStoreUnavailableException(exception);
                }

                // Another caller committed a baseline while this candidate was being checked; fall through and
                // re-evaluate the now-current baseline rather than publishing a stale first trust.
                try
                {
                    previous = _fingerprintRepository.Get(projectItemId, sourceKey);
                }
                catch (Exception exception)
                {
                    MarkFingerprintStoreFailed(exception, sourceItem.Id);
                    throw new FingerprintStoreUnavailableException(exception);
                }

                decision = _decisionService.Decide(
                    manifest,
                    previous,
                    HasPrimaryStream(sourceItem, source),
                    source.Path ?? sourceItem.ShortcutPath);
                if (decision.Kind is ProbeDecisionKind.SkipProbe or ProbeDecisionKind.TrustExisting)
                {
                    return BatchSourceOutcome.Skipped;
                }
            }
            else
            {
                return BatchSourceOutcome.Skipped;
            }
        }

        return await RunBatchProbeAsync(
            native,
            projectItemId,
            sourceItem,
            source,
            sourceKey,
            manifest,
            previous,
            stopSignal,
            scopeLibraryIds,
            scopeVerifier).ConfigureAwait(false);
    }

    private async Task<BatchSourceOutcome> RunBatchProbeAsync(
        IMediaSourceManager native,
        Guid projectItemId,
        BaseItem sourceItem,
        MediaSourceInfo source,
        string sourceKey,
        StrmManifest manifest,
        StrmFingerprint? previous,
        BatchStopSignal stopSignal,
        IReadOnlyList<Guid>? scopeLibraryIds,
        IBatchScopeVerifier? scopeVerifier)
    {
        if (stopSignal.IsStopped)
        {
            return BatchSourceOutcome.Revoked;
        }

        if (Coordinator.TryGetRunning(projectItemId, sourceKey, out var running))
        {
            return await JoinBatchSharedAsync(native, projectItemId, sourceItem, source, sourceKey, running!, stopSignal, isRunning: true, scopeLibraryIds, scopeVerifier)
                .ConfigureAwait(false);
        }

        ProbeReservation reservation;
        try
        {
            reservation = await Coordinator.AcquireAsync(projectItemId, sourceKey, manifest.ContentHash, stopSignal.CancellationToken)
                .ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            // The stop was confirmed while this candidate waited for a global permit; the work never started.
            return BatchSourceOutcome.Revoked;
        }

        if (!reservation.IsOwner)
        {
            return await JoinBatchSharedAsync(native, projectItemId, sourceItem, source, sourceKey, reservation.Item, stopSignal, reservation.IsRunning, scopeLibraryIds, scopeVerifier)
                .ConfigureAwait(false);
        }

        var workItem = reservation.Item;
        if (stopSignal.IsStopped)
        {
            Coordinator.Abandon(workItem);
            return BatchSourceOutcome.Revoked;
        }

        try
        {
            // Re-read the current native source, manifest and baseline after obtaining the execution opportunity,
            // exactly like the playback owner loop, so a queued candidate never probes a stale decision.
            BatchAdmission admission;
            try
            {
                admission = await AdmitBatchOwnerAsync(native, projectItemId, sourceItem, source, sourceKey, workItem, stopSignal, scopeLibraryIds, scopeVerifier)
                    .ConfigureAwait(false);
            }
            catch (FingerprintStoreUnavailableException)
            {
                Coordinator.Abandon(workItem);
                throw;
            }

            switch (admission.Kind)
            {
                case BatchAdmissionKind.Revoked:
                    Coordinator.Abandon(workItem);
                    return BatchSourceOutcome.Revoked;
                case BatchAdmissionKind.NotProcessed:
                    Coordinator.Abandon(workItem);
                    return BatchSourceOutcome.NotProcessed;
                case BatchAdmissionKind.CheckStageIncomplete:
                    Coordinator.Abandon(workItem);
                    return BatchSourceOutcome.CheckStageIncomplete;
                case BatchAdmissionKind.Skipped:
                    Coordinator.Abandon(workItem);
                    return BatchSourceOutcome.Skipped;
                case BatchAdmissionKind.Missing:
                    Coordinator.Abandon(workItem);
                    return BatchSourceOutcome.Missing;
                case BatchAdmissionKind.FirstTrust:
                    Coordinator.Abandon(workItem);
                    return BatchSourceOutcome.FirstTrust;
                case BatchAdmissionKind.Joined:
                    Coordinator.Abandon(workItem);
                    return await JoinBatchSharedAsync(native, projectItemId, sourceItem, source, sourceKey, admission.Item!, stopSignal, isRunning: true, scopeLibraryIds, scopeVerifier)
                        .ConfigureAwait(false);
                default:
                    manifest = admission.Manifest!;
                    previous = admission.Previous;
                    source = admission.Source!;
                    workItem.ManifestContentHash = manifest.ContentHash;
                    break;
            }

            var tracker = new ProbeStartTracker();
            ProbeExecutionOutcome outcome;
            try
            {
                // The batch stop token is deliberately not passed to the native probe: an actually started probe
                // always finishes and can still commit its verified result. CancellationToken.None matches playback.
                outcome = await ExecuteProbeAsync(
                    native,
                    projectItemId,
                    sourceItem,
                    source,
                    sourceKey,
                    null,
                    false,
                    CancellationToken.None,
                    manifest,
                    previous,
                    workItem,
                    stopSignal,
                    tracker).ConfigureAwait(false);
            }
            catch (BatchStopRejectedException)
            {
                Coordinator.Abandon(workItem);
                return BatchSourceOutcome.Revoked;
            }
            catch (ProbeStartRejectedException)
            {
                // A same-source execution started between registration and the matching call. Re-evaluate the
                // current version instead of running a duplicate native probe.
                Coordinator.Abandon(workItem);
                return await RecheckBatchSourceAsync(native, projectItemId, sourceItem, source, sourceKey, stopSignal, scopeLibraryIds, scopeVerifier)
                    .ConfigureAwait(false);
            }
            catch (Exception exception)
            {
                Coordinator.Fail(workItem, exception);
                return BatchSourceOutcome.ProbeIncomplete;
            }
            finally
            {
                if (tracker.Started)
                {
                    stopSignal.EndProbe();
                }
            }

            if (outcome.FingerprintStoreUnavailable)
            {
                Coordinator.Complete(workItem, outcome.Source);
                throw new FingerprintStoreUnavailableException();
            }

            Coordinator.Complete(workItem, outcome.Source, outcome.Committed);
            return outcome.Committed ? BatchSourceOutcome.Probed : BatchSourceOutcome.ProbeIncomplete;
        }
        catch (FingerprintStoreUnavailableException)
        {
            throw;
        }
        catch (Exception exception)
        {
            Coordinator.Fail(workItem, exception);
            throw;
        }
    }

    private async Task<BatchSourceOutcome> RecheckBatchSourceAsync(
        IMediaSourceManager native,
        Guid projectItemId,
        BaseItem sourceItem,
        MediaSourceInfo source,
        string sourceKey,
        BatchStopSignal stopSignal,
        IReadOnlyList<Guid>? scopeLibraryIds,
        IBatchScopeVerifier? scopeVerifier)
    {
        if (stopSignal.IsStopped)
        {
            return BatchSourceOutcome.Revoked;
        }

        var currentSources = native.GetStaticMediaSources(sourceItem, false);
        var current = PickOwnSource(sourceItem, currentSources);
        if (current is null)
        {
            return BatchSourceOutcome.Missing;
        }

        return await CheckBatchSourceAsync(native, projectItemId, sourceItem, current, sourceKey, stopSignal, scopeLibraryIds, scopeVerifier)
            .ConfigureAwait(false);
    }

    private async Task<BatchSourceOutcome> JoinBatchSharedAsync(
        IMediaSourceManager native,
        Guid projectItemId,
        BaseItem sourceItem,
        MediaSourceInfo source,
        string sourceKey,
        ProbeWorkItem shared,
        BatchStopSignal stopSignal,
        bool isRunning,
        IReadOnlyList<Guid>? scopeLibraryIds,
        IBatchScopeVerifier? scopeVerifier)
    {
        BatchSharedJoinBarrier?.Invoke();
        try
        {
            if (isRunning)
            {
                // A same-source probe that actually started is not cancelled by the batch stop. Wait for it to
                // settle (native save, verification, conditional commit) before this candidate returns, even when
                // the batch stop was already confirmed. CancellationToken.None keeps the batch stop out of the
                // already started execution, exactly like playback.
                await shared.Result.ConfigureAwait(false);
            }
            else
            {
                // The shared owner is still preparing and has not reached the matching native call. Waiting for a
                // preparing owner is not sharing a running probe, so the batch stop may end this wait without
                // cancelling the other caller's work.
                await shared.Result.WaitAsync(stopSignal.CancellationToken).ConfigureAwait(false);
            }
        }
        catch (OperationCanceledException) when (!isRunning && stopSignal.IsStopped)
        {
            // The batch stopped while waiting for a preparing owner. The other caller's work is not cancelled.
            return BatchSourceOutcome.Revoked;
        }
        catch (Exception)
        {
            // The shared probe failed. Re-evaluate the current version below instead of reusing its failure.
        }

        if (isRunning && shared.Committed == true && SharedCommitMatchesCurrentVersion(sourceItem, shared))
        {
            // This candidate joined a same-source probe that actually ran, saved and conditionally committed the
            // current version during this run. Associate that this-run reliable success instead of counting the
            // wait return or an existing fingerprint as success.
            return BatchSourceOutcome.Probed;
        }

        if (stopSignal.IsStopped)
        {
            return BatchSourceOutcome.Revoked;
        }

        // Re-check the current scope after the shared wait; the object may have left the selected libraries.
        if (scopeVerifier is not null && scopeLibraryIds is not null && !scopeVerifier.IsInScope(sourceItem, scopeLibraryIds))
        {
            return BatchSourceOutcome.Missing;
        }

        // A shared probe never proves this candidate's own current version. Re-read the current source and
        // re-evaluate it, so a shared reliable success is not counted from a wait return alone.
        var currentSources = native.GetStaticMediaSources(sourceItem, false);
        var current = PickOwnSource(sourceItem, currentSources);
        if (current is null)
        {
            return BatchSourceOutcome.Missing;
        }

        return await CheckBatchSourceAsync(native, projectItemId, sourceItem, current, sourceKey, stopSignal, scopeLibraryIds, scopeVerifier)
            .ConfigureAwait(false);
    }

    private bool SharedCommitMatchesCurrentVersion(BaseItem sourceItem, ProbeWorkItem shared)
    {
        var readResult = _manifestReader.Read(sourceItem.Path);
        return readResult.Status == ManifestReadStatus.Supported
            && readResult.Manifest is { } manifest
            && string.Equals(manifest.ContentHash, shared.ManifestContentHash, StringComparison.Ordinal);
    }

    private async Task<BatchAdmission> AdmitBatchOwnerAsync(
        IMediaSourceManager native,
        Guid projectItemId,
        BaseItem sourceItem,
        MediaSourceInfo source,
        string sourceKey,
        ProbeWorkItem workItem,
        BatchStopSignal stopSignal,
        IReadOnlyList<Guid>? scopeLibraryIds,
        IBatchScopeVerifier? scopeVerifier)
    {
        if (!_settings.Enabled || IsFingerprintStoreUnavailable)
        {
            return BatchAdmission.NotProcessed();
        }

        if (stopSignal.IsStopped)
        {
            return BatchAdmission.Revoked();
        }

        // Re-check the current library relationship after the execution opportunity was obtained. A candidate that
        // left the selected scope, was deleted or changed type while queued must not be probed from a stale object.
        if (scopeVerifier is not null && scopeLibraryIds is not null && !scopeVerifier.IsInScope(sourceItem, scopeLibraryIds))
        {
            return BatchAdmission.Missing();
        }
        var currentSources = native.GetStaticMediaSources(sourceItem, false);
        var currentSource = PickOwnSource(sourceItem, currentSources);
        if (currentSource is null)
        {
            return BatchAdmission.Missing();
        }

        if (Coordinator.TryGetRunning(projectItemId, sourceKey, out var running))
        {
            return BatchAdmission.Joined(running!);
        }

        var readResult = _manifestReader.Read(sourceItem.Path);
        if (readResult.Status is ManifestReadStatus.Invalid or ManifestReadStatus.Unavailable)
        {
            return BatchAdmission.CheckStageIncomplete();
        }

        if (readResult.Status != ManifestReadStatus.Supported || readResult.Manifest is not { } currentManifest)
        {
            return BatchAdmission.NotProcessed();
        }

        StrmFingerprint? currentPrevious;
        try
        {
            currentPrevious = _fingerprintRepository.Get(projectItemId, sourceKey);
        }
        catch (Exception exception)
        {
            MarkFingerprintStoreFailed(exception, sourceItem.Id);
            throw new FingerprintStoreUnavailableException(exception);
        }

        var decision = _decisionService.Decide(
            currentManifest,
            currentPrevious,
            HasPrimaryStream(sourceItem, currentSource),
            currentSource.Path ?? sourceItem.ShortcutPath);

        if (decision.Kind is ProbeDecisionKind.SkipProbe or ProbeDecisionKind.TrustExisting)
        {
            if (!ManifestIsStillCurrent(sourceItem.Path, currentManifest))
            {
                return BatchAdmission.CheckStageIncomplete();
            }

            if (decision.Kind == ProbeDecisionKind.TrustExisting)
            {
                try
                {
                    if (_fingerprintRepository.TryCommit(CreateFingerprint(projectItemId, sourceKey, currentManifest), expectedPrevious: null))
                    {
                        return BatchAdmission.FirstTrust();
                    }
                }
                catch (Exception exception)
                {
                    MarkFingerprintStoreFailed(exception, sourceItem.Id);
                    throw new FingerprintStoreUnavailableException(exception);
                }

                return BatchAdmission.Skipped();
            }

            return BatchAdmission.Skipped();
        }

        return BatchAdmission.Start(currentManifest, currentPrevious, currentSource);
    }

    private static MediaSourceInfo? PickOwnSource(BaseItem sourceItem, IReadOnlyList<MediaSourceInfo> sources)
    {
        var ownKey = sourceItem.Id.ToString("N", CultureInfo.InvariantCulture);
        var own = sources.FirstOrDefault(candidate => HasSourceId(candidate, ownKey));
        if (own is not null)
        {
            return own;
        }

        return sources.Count == 1 ? sources[0] : null;
    }

    private async Task<MediaSourceInfo?> CheckSourceCoreAsync(
        IMediaSourceManager native,
        Guid projectItemId,
        BaseItem sourceItem,
        MediaSourceInfo source,
        string sourceKey,
        bool isPlaybackContext,
        User? user,
        bool enablePathSubstitution,
        CancellationToken cancellationToken)
    {
        var sourceId = source.Id;
        var isStrm = IsStrm(sourceItem);
        var readResult = isStrm ? _manifestReader.Read(sourceItem.Path) : ManifestReadResult.Unsupported;
        if (readResult.Status != ManifestReadStatus.Supported || readResult.Manifest is not { } manifest)
        {
            return await GetSourceWithNativeAsync(native, sourceItem, sourceId, allowMediaProbe: true, user, enablePathSubstitution, cancellationToken)
                .ConfigureAwait(false);
        }

        StrmFingerprint? previous;
        try
        {
            previous = _fingerprintRepository.Get(projectItemId, sourceKey);
        }
        catch (Exception exception)
        {
            MarkFingerprintStoreFailed(exception, sourceItem.Id);
            return await GetSourceWithNativeAsync(native, sourceItem, sourceId, allowMediaProbe: true, user, enablePathSubstitution, cancellationToken)
                .ConfigureAwait(false);
        }

        var decision = _decisionService.Decide(
            manifest,
            previous,
            HasPrimaryStream(sourceItem, source),
            source.Path ?? sourceItem.ShortcutPath);

        if (decision.Kind is ProbeDecisionKind.SkipProbe or ProbeDecisionKind.TrustExisting)
        {
            if (!ManifestIsStillCurrent(sourceItem.Path, manifest))
            {
                _logger.LogInformation("STRM changed during playback decision for item {ItemId}, source {SourceId}; delegating to Jellyfin.", projectItemId, sourceKey);
                return await GetSourceWithNativeAsync(native, sourceItem, sourceId, allowMediaProbe: true, user, enablePathSubstitution, cancellationToken)
                    .ConfigureAwait(false);
            }

            if (decision.Kind == ProbeDecisionKind.TrustExisting)
            {
                var candidate = CreateFingerprint(projectItemId, sourceKey, manifest);
                try
                {
                    if (!_fingerprintRepository.TryCommit(candidate, expectedPrevious: null))
                    {
                        previous = _fingerprintRepository.Get(projectItemId, sourceKey);
                        decision = _decisionService.Decide(
                            manifest,
                            previous,
                            HasPrimaryStream(sourceItem, source),
                            source.Path ?? sourceItem.ShortcutPath);
                        if (decision.Kind == ProbeDecisionKind.RequireProbe)
                        {
                            return await ProbeAndVerifyAsync(
                                native,
                                projectItemId,
                                sourceItem,
                                source,
                                sourceKey,
                                user,
                                enablePathSubstitution,
                                cancellationToken,
                                manifest,
                                previous,
                                isPlaybackContext).ConfigureAwait(false);
                        }
                    }
                }
                catch (Exception exception)
                {
                    MarkFingerprintStoreFailed(exception, sourceItem.Id);
                    return await GetSourceWithNativeAsync(native, sourceItem, sourceId, allowMediaProbe: true, user, enablePathSubstitution, cancellationToken)
                        .ConfigureAwait(false);
                }
            }

            LogDecision("reused saved media information", projectItemId, sourceKey, decision.Reason);
            return null;
        }

        return await ProbeAndVerifyAsync(
            native,
            projectItemId,
            sourceItem,
            source,
            sourceKey,
            user,
            enablePathSubstitution,
            cancellationToken,
            manifest,
            previous,
            isPlaybackContext).ConfigureAwait(false);
    }

    /// <summary>
    /// Re-evaluates an owner at the moment it obtains an execution opportunity. It re-reads the current native
    /// source for this caller and then the current manifest and trusted baseline, instead of probing the decision
    /// captured before it waited. Acquiring a permit immediately does not prove the entry snapshot is still current:
    /// a same-source execution can complete between the permit acquisition and the registration, so every owner
    /// returns to this single action loop. A preparing or running same-source probe is joined rather than duplicated.
    /// </summary>
    private async Task<ProbeAdmission> AdmitOwnerAsync(
        IMediaSourceManager native,
        Guid projectItemId,
        BaseItem sourceItem,
        MediaSourceInfo source,
        string sourceKey,
        bool isPlaybackContext,
        User? user,
        bool enablePathSubstitution,
        CancellationToken cancellationToken,
        ProbeWorkItem workItem)
    {
        while (true)
        {
            if (!CanOptimize(isPlaybackContext))
            {
                // Release the unused owner reservation before any native delegation so a permit is never held
                // while Jellyfin performs ordinary work. Settlement is idempotent.
                Coordinator.Abandon(workItem);
                var delegated = await GetSourceWithNativeAsync(native, sourceItem, source.Id, allowMediaProbe: true, user, enablePathSubstitution, cancellationToken)
                    .ConfigureAwait(false);
                return ProbeAdmission.Delegate(delegated);
            }

            // Always read the current native source for this caller first (its user, source id and path
            // substitution). A decision must never be based on the pre-queue snapshot or on item.ShortcutPath alone.
            var currentSource = await GetSourceWithNativeAsync(native, sourceItem, source.Id, allowMediaProbe: false, user, enablePathSubstitution, cancellationToken)
                .ConfigureAwait(false);

            // The current source read is asynchronous; the plugin may have been disabled or the fingerprint
            // store may have faulted while it was in flight. Re-check the applicable enable/disable state before
            // deciding, exactly like the manifest and trusted baseline below.
            if (!CanOptimize(isPlaybackContext))
            {
                Coordinator.Abandon(workItem);
                var disabledDelegation = await GetSourceWithNativeAsync(native, sourceItem, source.Id, allowMediaProbe: true, user, enablePathSubstitution, cancellationToken)
                    .ConfigureAwait(false);
                return ProbeAdmission.Delegate(disabledDelegation);
            }

            // The native read is asynchronous: a same-source execution may have started while it was in flight.
            // Re-check after the await and join it instead of starting a duplicate.
            if (Coordinator.TryGetRunning(projectItemId, sourceKey, out var running))
            {
                Coordinator.Abandon(workItem);
                return ProbeAdmission.Joined(running!);
            }

            // Read the current manifest and trusted baseline after the current source read so the decision uses
            // the same currentness point as the native source that will be probed.
            var readResult = IsStrm(sourceItem) ? _manifestReader.Read(sourceItem.Path) : ManifestReadResult.Unsupported;
            if (readResult.Status != ManifestReadStatus.Supported || readResult.Manifest is not { } currentManifest)
            {
                Coordinator.Abandon(workItem);
                var delegated = await GetSourceWithNativeAsync(native, sourceItem, source.Id, allowMediaProbe: true, user, enablePathSubstitution, cancellationToken)
                    .ConfigureAwait(false);
                return ProbeAdmission.Delegate(delegated);
            }

            StrmFingerprint? currentPrevious;
            try
            {
                currentPrevious = _fingerprintRepository.Get(projectItemId, sourceKey);
            }
            catch (Exception exception)
            {
                MarkFingerprintStoreFailed(exception, sourceItem.Id);
                Coordinator.Abandon(workItem);
                var delegated = await GetSourceWithNativeAsync(native, sourceItem, source.Id, allowMediaProbe: true, user, enablePathSubstitution, cancellationToken)
                    .ConfigureAwait(false);
                return ProbeAdmission.Delegate(delegated);
            }

            var currentDecision = _decisionService.Decide(
                currentManifest,
                currentPrevious,
                HasPrimaryStream(sourceItem, currentSource),
                currentSource.Path ?? sourceItem.ShortcutPath);

            if (currentDecision.Kind is ProbeDecisionKind.SkipProbe or ProbeDecisionKind.TrustExisting)
            {
                // The first-trust exception is the only no-probe initialisation, but it must still describe the
                // current STRM version. A change after the decision is never published as a trusted baseline.
                if (!ManifestIsStillCurrent(sourceItem.Path, currentManifest))
                {
                    _logger.LogInformation("STRM changed during owner admission for item {ItemId}, source {SourceId}; delegating to Jellyfin.", projectItemId, sourceKey);
                    Coordinator.Abandon(workItem);
                    var delegated = await GetSourceWithNativeAsync(native, sourceItem, source.Id, allowMediaProbe: true, user, enablePathSubstitution, cancellationToken)
                        .ConfigureAwait(false);
                    return ProbeAdmission.Delegate(delegated);
                }

                if (currentDecision.Kind == ProbeDecisionKind.TrustExisting)
                {
                    try
                    {
                        if (!_fingerprintRepository.TryCommit(CreateFingerprint(projectItemId, sourceKey, currentManifest), expectedPrevious: null))
                        {
                            // Another caller committed a baseline while this owner was admitting. Re-evaluate the
                            // now-current baseline instead of publishing a stale first trust.
                            continue;
                        }
                    }
                    catch (Exception exception)
                    {
                        MarkFingerprintStoreFailed(exception, sourceItem.Id);
                        Coordinator.Abandon(workItem);
                        var delegated = await GetSourceWithNativeAsync(native, sourceItem, source.Id, allowMediaProbe: true, user, enablePathSubstitution, cancellationToken)
                            .ConfigureAwait(false);
                        return ProbeAdmission.Delegate(delegated);
                    }
                }

                LogDecision("reused saved media information", projectItemId, sourceKey, currentDecision.Reason);
                Coordinator.Abandon(workItem);
                return ProbeAdmission.Delegate(null);
            }

            return ProbeAdmission.Start(currentManifest, currentPrevious, currentSource);
        }
    }

    private async Task<MediaSourceInfo?> ProbeAndVerifyAsync(
        IMediaSourceManager native,
        Guid projectItemId,
        BaseItem sourceItem,
        MediaSourceInfo previousSource,
        string sourceKey,
        User? user,
        bool enablePathSubstitution,
        CancellationToken cancellationToken,
        StrmManifest manifest,
        StrmFingerprint? previous,
        bool isPlaybackContext)
    {
        if (Coordinator.TryGetRunning(projectItemId, sourceKey, out var running))
        {
            return await JoinSharedAsync(
                native,
                projectItemId,
                sourceItem,
                previousSource,
                sourceKey,
                user,
                enablePathSubstitution,
                cancellationToken,
                running!,
                isRunning: true,
                isPlaybackContext).ConfigureAwait(false);
        }

        var reservation = await Coordinator.AcquireAsync(projectItemId, sourceKey, manifest.ContentHash, cancellationToken)
            .ConfigureAwait(false);
        if (!reservation.IsOwner)
        {
            return await JoinSharedAsync(
                native,
                projectItemId,
                sourceItem,
                previousSource,
                sourceKey,
                user,
                enablePathSubstitution,
                cancellationToken,
                reservation.Item,
                reservation.IsRunning,
                isPlaybackContext).ConfigureAwait(false);
        }

        var workItem = reservation.Item;
        try
        {
            var admission = await AdmitOwnerAsync(
                native,
                projectItemId,
                sourceItem,
                previousSource,
                sourceKey,
                isPlaybackContext,
                user,
                enablePathSubstitution,
                cancellationToken,
                workItem).ConfigureAwait(false);

            switch (admission.Kind)
            {
                case ProbeAdmissionKind.Delegate:
                    // The admission already released the unused reservation; the permit is not held during
                    // ordinary native work.
                    return admission.Result;
                case ProbeAdmissionKind.Joined:
                    return await JoinSharedAsync(
                        native,
                        projectItemId,
                        sourceItem,
                        previousSource,
                        sourceKey,
                        user,
                        enablePathSubstitution,
                        cancellationToken,
                        admission.Item!,
                        isRunning: true,
                        isPlaybackContext).ConfigureAwait(false);
                default:
                    manifest = admission.Manifest!;
                    previous = admission.Previous;
                    previousSource = admission.Source!;
                    workItem.ManifestContentHash = manifest.ContentHash;
                    break;
            }

            MediaSourceInfo result;
            var committed = false;
            try
            {
                var outcome = await ExecuteProbeAsync(
                    native,
                    projectItemId,
                    sourceItem,
                    previousSource,
                    sourceKey,
                    user,
                    enablePathSubstitution,
                    cancellationToken,
                    manifest,
                    previous,
                    workItem).ConfigureAwait(false);
                result = outcome.Source;
                committed = outcome.Committed;
            }
            catch (ProbeStartRejectedException)
            {
                // A same-source execution started between the registration and the matching native call, so this
                // reservation no longer owns the start. Release it and re-evaluate the current version (which may
                // already be accepted) instead of running a duplicate native probe.
                Coordinator.Abandon(workItem);
                var current = _manifestReader.Read(sourceItem.Path);
                if (current.Status == ManifestReadStatus.Supported && current.Manifest is not null)
                {
                    return await CheckSourceCoreAsync(
                        native,
                        projectItemId,
                        sourceItem,
                        previousSource,
                        sourceKey,
                        isPlaybackContext,
                        user,
                        enablePathSubstitution,
                        cancellationToken).ConfigureAwait(false);
                }

                return await GetSourceWithNativeAsync(native, sourceItem, previousSource.Id, allowMediaProbe: true, user, enablePathSubstitution, cancellationToken)
                    .ConfigureAwait(false);
            }

            Coordinator.Complete(workItem, result, committed);
            return result;
        }
        catch (Exception exception)
        {
            // Every owner path after obtaining a permit is protected here: admission, delegation, execution,
            // cancellation and validation. Settlement is idempotent, so an already abandoned reservation is a
            // no-op and the global permit/registration can never leak. The original exception is preserved.
            Coordinator.Fail(workItem, exception);
            throw;
        }
    }

    /// <summary>
    /// Waits for a same-source probe that is already preparing or actually running, then re-reads the current
    /// manifest, fingerprint and native source instead of reusing the other caller's media source. This keeps
    /// each caller's authorization, source selection and path substitution intact.
    /// </summary>
    private async Task<MediaSourceInfo?> JoinSharedAsync(
        IMediaSourceManager native,
        Guid projectItemId,
        BaseItem sourceItem,
        MediaSourceInfo source,
        string sourceKey,
        User? user,
        bool enablePathSubstitution,
        CancellationToken cancellationToken,
        ProbeWorkItem shared,
        bool isRunning,
        bool isPlaybackContext)
    {
        SharedJoinBarrier?.Invoke();
        if (isRunning)
        {
            _logger.LogInformation(
                "Joined a running native probe for item {ItemId}, source_key {SourceId}; running probes {Running}, active permits {Active}.",
                projectItemId,
                sourceKey,
                Coordinator.RunningCount,
                Coordinator.ActivePermits);
        }
        else
        {
            _logger.LogInformation(
                "Waiting for a same-source probe that is still preparing for item {ItemId}, source_key {SourceId}; running probes {Running}, active permits {Active}.",
                projectItemId,
                sourceKey,
                Coordinator.RunningCount,
                Coordinator.ActivePermits);
        }

        try
        {
            await shared.Result.WaitAsync(cancellationToken).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            // The waiting caller exited. The already started probe is not cancelled and still completes on its own.
            throw;
        }
        catch (Exception)
        {
            var current = _manifestReader.Read(sourceItem.Path);
            var currentHash = current.Status == ManifestReadStatus.Supported ? current.Manifest!.ContentHash : null;
            if (currentHash is not null && string.Equals(currentHash, shared.ManifestContentHash, StringComparison.Ordinal))
            {
                // The same version failed. Surface the same failure instead of silently retrying.
                throw;
            }

            // The shared probe verified a different version; fall through and re-evaluate the current one.
        }

        // Re-read the current native source, manifest, fingerprint and configuration so this caller never reuses
        // another caller's response and re-admits if the plugin was disabled while it waited.
        var currentSource = await GetSourceWithNativeAsync(native, sourceItem, source.Id, allowMediaProbe: false, user, enablePathSubstitution, cancellationToken)
            .ConfigureAwait(false);
        return await CheckSourceAsync(
            native,
            projectItemId,
            sourceItem,
            currentSource,
            sourceKey,
            allowMediaProbe: true,
            user,
            enablePathSubstitution,
            cancellationToken,
            isPlaybackContext).ConfigureAwait(false);
    }

    private async Task<ProbeExecutionOutcome> ExecuteProbeAsync(
        IMediaSourceManager native,
        Guid projectItemId,
        BaseItem sourceItem,
        MediaSourceInfo previousSource,
        string sourceKey,
        User? user,
        bool enablePathSubstitution,
        CancellationToken cancellationToken,
        StrmManifest manifest,
        StrmFingerprint? previous,
        ProbeWorkItem workItem,
        BatchStopSignal? stopSignal = null,
        ProbeStartTracker? tracker = null)
    {
        var requiredStreamType = GetRequiredStreamType(sourceItem);
        var started = 0;
        void MarkStarted()
        {
            // Invoked from the encoder proxy at the verified matching native call, i.e. the real probe start.
            if (Interlocked.Exchange(ref started, 1) != 0)
            {
                return;
            }

            if (stopSignal is not null && !stopSignal.TryBeginProbe())
            {
                // The batch stop was confirmed before the matching native call. Abort the native call so no
                // plugin probe actually starts; the owner settles this reservation as not started.
                throw new BatchStopRejectedException(projectItemId, sourceKey);
            }

            if (!Coordinator.TryMarkStarted(workItem, out _))
            {
                // Another caller owns this key (or this reservation is no longer the current owner). Abort the
                // native call instead of publishing a duplicate running probe; the exception propagates through
                // the encoder proxy and this reservation is settled as a failure.
                if (stopSignal is not null)
                {
                    // The stop boundary already counted this probe as in flight, but it never actually started.
                    stopSignal.EndProbe();
                }

                _logger.LogWarning(
                    "A duplicate same-source native probe start was rejected for item {ItemId}, source {SourceId}; aborting the redundant native call.",
                    projectItemId,
                    sourceKey);
                throw new ProbeStartRejectedException(projectItemId, sourceKey);
            }

            if (tracker is not null)
            {
                tracker.Started = true;
            }

            _logger.LogInformation(
                "Native STRM probe started for item {ItemId}, source_key {SourceId}; running probes {Running}, active permits {Active}.",
                projectItemId,
                sourceKey,
                Coordinator.RunningCount,
                Coordinator.ActivePermits);
        }

        using var probeContext = ProbeExecutionContext.Begin(projectItemId, sourceItem.Id, sourceKey, manifest.Url, requiredStreamType, MarkStarted);
        IReadOnlyList<MediaSourceInfo> sources;
        try
        {
            sources = await native.GetPlaybackMediaSources(sourceItem, user, true, enablePathSubstitution, cancellationToken)
                .ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            _logger.LogInformation("Native STRM probe canceled for item {ItemId}, source {SourceId}; matching encoder calls {ProbeCalls}, fingerprint retained.", projectItemId, sourceKey, probeContext.MatchingCallCount);
            throw;
        }
        catch (Exception)
        {
            _logger.LogWarning("Native STRM probe failed for item {ItemId}, source {SourceId}; matching encoder calls {ProbeCalls}, fingerprint retained.", projectItemId, sourceKey, probeContext.MatchingCallCount);
            throw;
        }

        var latestRead = _manifestReader.Read(sourceItem.Path);
        var latestManifest = latestRead.Status == ManifestReadStatus.Supported ? latestRead.Manifest : null;
        var currentUrlStillMatches = latestManifest is not null
            && string.Equals(latestManifest.Url, manifest.Url, StringComparison.Ordinal);
        var resultSource = sources.FirstOrDefault(candidate => HasSourceId(candidate, sourceKey));
        var itemAddressMatches = string.Equals(sourceItem.ShortcutPath, manifest.Url, StringComparison.Ordinal);
        var previousNativeUrl = previousSource.Path ?? sourceItem.ShortcutPath;
        var urlChanged = (previous is not null && !string.Equals(previous.UrlHash, manifest.UrlHash, StringComparison.Ordinal))
            || (previousNativeUrl is not null && !string.Equals(previousNativeUrl, manifest.Url, StringComparison.Ordinal));
        var returnedPrimaryMatchesProbe = resultSource?.MediaStreams?
            .FirstOrDefault(stream => stream.Type == requiredStreamType) is { } returnedPrimary
            && probeContext.IsPersistedProbeResult(returnedPrimary);
        var addressPersistenceConfirmed = !urlChanged || probeContext.HasPersistedAddress;
        var persistedResultIsUsable = resultSource is not null
            && HasPrimaryStream(sourceItem, resultSource)
            && itemAddressMatches
            && probeContext.HasPersistedPrimaryResult
            && returnedPrimaryMatchesProbe
            && addressPersistenceConfirmed;

        if (!currentUrlStillMatches || latestManifest!.ContentHash != manifest.ContentHash)
        {
            _logger.LogWarning(
                "STRM manifest changed during native probe for item {ItemId}, source {SourceId}; matching calls {ProbeCalls}, fingerprint retained.",
                projectItemId,
                sourceKey,
                probeContext.MatchingCallCount);
            throw new InvalidOperationException("The STRM changed during Jellyfin's native probe; playback must retry with the current manifest.");
        }

        if (!persistedResultIsUsable)
        {
            _logger.LogWarning(
                "Native probe result was not accepted for item {ItemId}, source {SourceId}; calls {ProbeCalls}, encoder primary {EncoderPrimary}, persisted primary {PersistedPrimary}, address persisted {AddressPersisted}, returned primary matches probe {ReturnedPrimaryMatches}.",
                projectItemId,
                sourceKey,
                probeContext.MatchingCallCount,
                probeContext.HasSuccessfulPrimaryResult,
                probeContext.HasPersistedPrimaryResult,
                probeContext.HasPersistedAddress,
                returnedPrimaryMatchesProbe);
            throw new InvalidOperationException("Jellyfin did not save a usable media source for the current STRM version.");
        }

        var candidate = CreateFingerprint(projectItemId, sourceKey, manifest);
        var committed = false;
        var storeUnavailable = false;
        try
        {
            if (_fingerprintRepository.TryCommit(candidate, previous))
            {
                committed = true;
                _logger.LogInformation(
                    "Native probe accepted for STRM item {ItemId}, source {SourceId}; calls {ProbeCalls}, address persisted {AddressPersisted}, fingerprint committed.",
                    projectItemId,
                    sourceKey,
                    probeContext.MatchingCallCount,
                    probeContext.HasPersistedAddress);
            }
            else
            {
                _logger.LogWarning("Native probe result was not committed for item {ItemId}, source {SourceId}; the accepted baseline changed.", projectItemId, sourceKey);
            }
        }
        catch (Exception exception)
        {
            // The native result is already persisted and verified. Do not repeat a successful probe because the history write failed.
            MarkFingerprintStoreFailed(exception, sourceItem.Id);
            storeUnavailable = true;
            _logger.LogWarning(
                "Native STRM probe completed for item {ItemId}, source {SourceId}, but its SQLite fingerprint write failed; matching calls {ProbeCalls}, fingerprint retained.",
                projectItemId,
                sourceKey,
                probeContext.MatchingCallCount);
        }

        return new ProbeExecutionOutcome(resultSource!, committed, storeUnavailable);
    }

    /// <summary>
    /// Gets or sets a test-only hook invoked in the batch decision immediately after the current manifest has
    /// been read and before its currentness is re-checked. It lets a deterministic regression change the STRM
    /// during the decision. It is <c>null</c> in production.
    /// </summary>
    internal Action? BatchDecisionBarrier { get; set; }

    /// <summary>
    /// Gets or sets a test-only barrier invoked when a batch caller joins an existing same-source probe. It lets
    /// a deterministic regression observe the shared wait. It is <c>null</c> in production.
    /// </summary>
    internal Action? BatchSharedJoinBarrier { get; set; }

    /// <summary>
    /// Gets a value indicating whether the SQLite fingerprint store has faulted and optimization is latched off
    /// until the next restart.
    /// </summary>
    public bool IsFingerprintStoreUnavailable => Volatile.Read(ref _fingerprintStoreFailed) != 0;

    private async Task<MediaSourceInfo> GetSourceWithNativeAsync(
        IMediaSourceManager native,
        BaseItem sourceItem,
        string? sourceId,
        bool allowMediaProbe,
        User? user,
        bool enablePathSubstitution,
        CancellationToken cancellationToken)
    {
        var sources = await native.GetPlaybackMediaSources(sourceItem, user, allowMediaProbe, enablePathSubstitution, cancellationToken)
            .ConfigureAwait(false);
        var source = sourceId is null ? null : sources.FirstOrDefault(candidate => HasSourceId(candidate, sourceId));
        if (source is null)
        {
            _logger.LogWarning("Jellyfin did not return source {SourceId} after native delegation for item {ItemId}.", sourceId ?? "unidentified", sourceItem.Id);
            throw new InvalidOperationException("Jellyfin did not return the delegated media source; playback must retry.");
        }

        return source;
    }

    private List<SourceItem> ResolveVisibleSourceItems(
        BaseItem requestedItem,
        User? user,
        IReadOnlyList<MediaSourceInfo> sources,
        out bool allResolved)
    {
        var result = new List<SourceItem>(sources.Count);
        var seen = new HashSet<Guid>();
        allResolved = true;
        foreach (var source in sources)
        {
            if (!Guid.TryParse(source.Id, out var sourceId) || !seen.Add(sourceId))
            {
                allResolved = false;
                continue;
            }

            var sourceItem = sourceId == requestedItem.Id
                ? requestedItem
                : _libraryManager?.GetItemById<BaseItem>(sourceId, user);
            if (sourceItem is null)
            {
                allResolved = false;
                continue;
            }

            result.Add(new SourceItem(source, sourceItem, sourceId));
        }

        return result;
    }

    private void EnsureVisibleSourcesAndManifestsCurrent(
        BaseItem requestedItem,
        IReadOnlyList<SourceItem> checkedSources,
        IReadOnlyDictionary<Guid, ManifestReadResult> checkedManifests,
        IReadOnlyList<MediaSourceInfo> currentSources)
    {
        var currentById = new Dictionary<Guid, MediaSourceInfo>();
        foreach (var source in currentSources)
        {
            if (!Guid.TryParse(source.Id, out var sourceId) || !currentById.TryAdd(sourceId, source))
            {
                _logger.LogWarning("Jellyfin's visible media source set changed during STRM processing for item {ItemId}; playback must retry.", requestedItem.Id);
                throw new InvalidOperationException("Jellyfin's visible media source set changed during STRM processing; playback must retry.");
            }
        }

        if (currentById.Count != checkedSources.Count)
        {
            _logger.LogWarning("Jellyfin's visible media source set changed during STRM processing for item {ItemId}; playback must retry.", requestedItem.Id);
            throw new InvalidOperationException("Jellyfin's visible media source set changed during STRM processing; playback must retry.");
        }

        foreach (var entry in checkedSources)
        {
            if (!currentById.TryGetValue(entry.SourceId, out var currentSource))
            {
                _logger.LogWarning("Jellyfin no longer returned visible media source {SourceId} for item {ItemId}; playback must retry.", entry.SourceId, requestedItem.Id);
                throw new InvalidOperationException("Jellyfin's visible media source set changed during STRM processing; playback must retry.");
            }

            if (!checkedManifests.TryGetValue(entry.SourceId, out var expectedManifest))
            {
                continue;
            }

            var latestManifest = _manifestReader.Read(entry.Item.Path);
            if (!SameManifest(expectedManifest, latestManifest))
            {
                _logger.LogWarning("STRM manifest changed before playback sources were returned for item {ItemId}, source {SourceId}; playback must retry.", requestedItem.Id, entry.SourceId);
                throw new InvalidOperationException("A STRM changed while Jellyfin playback sources were being prepared; playback must retry.");
            }

            if (expectedManifest.Manifest is not { } manifest)
            {
                continue;
            }

            var currentUrl = currentSource.Path ?? entry.Item.ShortcutPath;
            if (!HasPrimaryStream(entry.Item, currentSource)
                || !string.Equals(currentUrl, manifest.Url, StringComparison.Ordinal))
            {
                _logger.LogWarning("The current Jellyfin source is not usable for STRM item {ItemId}, source {SourceId}; playback must retry.", requestedItem.Id, entry.SourceId);
                throw new InvalidOperationException("Jellyfin's current media source no longer matches the STRM manifest; playback must retry.");
            }
        }
    }

    private static bool SameManifest(ManifestReadResult expected, ManifestReadResult actual)
    {
        return expected.Status == actual.Status
            && string.Equals(expected.Manifest?.ContentHash, actual.Manifest?.ContentHash, StringComparison.Ordinal);
    }

    private bool CanOptimize(bool isPlaybackContext)
    {
        return _settings.Enabled
            && (!isPlaybackContext || _settings.PlaybackAutoCheck)
            && Volatile.Read(ref _fingerprintStoreFailed) == 0;
    }

    private void LogDecision(string action, Guid projectItemId, string sourceKey, ProbeDecisionReason reason)
    {
        if (_settings.DetailedLog)
        {
            _logger.LogInformation(
                "STRM source {Action} for project {ItemId}, source {SourceId}; reason {Reason}, plugin probe calls 0, Jellyfin GetMediaInfo calls observed {EncoderCallsTotal}.",
                action,
                projectItemId,
                sourceKey,
                reason,
                MediaEncoderDispatchProxy.GetMediaInfoCallCount);
            return;
        }

        _logger.LogInformation(
            "STRM source {Action} for project {ItemId}, source {SourceId}; reason {Reason}, plugin probe calls 0.",
            action,
            projectItemId,
            sourceKey,
            reason);
    }

    private void MarkFingerprintStoreFailed(Exception exception, Guid itemId)
    {
        if (Interlocked.Exchange(ref _fingerprintStoreFailed, 1) == 0)
        {
            _logger.LogWarning(
                "STRM fingerprint store became unavailable for item {ItemId}; failure category {FailureType}, optimization disabled until restart and native playback delegated.",
                itemId,
                exception.GetType().Name);
        }
    }

    private bool ManifestIsStillCurrent(string path, StrmManifest expected)
    {
        var latestRead = _manifestReader.Read(path);
        return latestRead.Status == ManifestReadStatus.Supported
            && latestRead.Manifest is { } latest
            && latest.ContentHash == expected.ContentHash;
    }

    private static IReadOnlyList<SourceItem> FilterSupportedSourceItems(IEnumerable<SourceItem> sourceItems, IStrmManifestReader reader)
    {
        return sourceItems.Where(entry => IsStrm(entry.Item)
            && reader.Read(entry.Item.Path).Status == ManifestReadStatus.Supported).ToArray();
    }

    private static Guid GetProjectId(BaseItem item)
    {
        return item is Video video && video.PrimaryVersionId is { } primaryVersionId
            ? primaryVersionId
            : item.Id;
    }

    private static StrmFingerprint CreateFingerprint(Guid projectItemId, string sourceKey, StrmManifest manifest)
    {
        return new StrmFingerprint(projectItemId, sourceKey, manifest.UrlHash, manifest.Sha1, manifest.Size);
    }

    private static bool IsStrm(BaseItem item)
    {
        return !string.IsNullOrEmpty(item.Path) && item.Path.EndsWith(".strm", StringComparison.OrdinalIgnoreCase);
    }

    private static bool HasPrimaryStream(BaseItem item, MediaSourceInfo source)
    {
        var requiredStream = GetRequiredStreamType(item);
        return source.MediaStreams?.Any(stream => stream.Type == requiredStream) == true;
    }

    private static MediaStreamType GetRequiredStreamType(BaseItem item)
    {
        return item.MediaType == MediaType.Audio ? MediaStreamType.Audio : MediaStreamType.Video;
    }

    private static bool HasSourceId(MediaSourceInfo source, string sourceId)
    {
        return Guid.TryParse(source.Id, out var parsedSourceId)
            && string.Equals(parsedSourceId.ToString("N", CultureInfo.InvariantCulture), sourceId, StringComparison.OrdinalIgnoreCase);
    }

    private static Task<IReadOnlyList<MediaSourceInfo>> DelegateAsync(
        IMediaSourceManager native,
        BaseItem item,
        User? user,
        bool allowMediaProbe,
        bool enablePathSubstitution,
        CancellationToken cancellationToken)
    {
        return native.GetPlaybackMediaSources(item, user, allowMediaProbe, enablePathSubstitution, cancellationToken);
    }

    private sealed record SourceItem(MediaSourceInfo Source, BaseItem Item, Guid SourceId);

    private enum ProbeAdmissionKind
    {
        Start,
        Delegate,
        Joined
    }

    private sealed record ProbeAdmission(
        ProbeAdmissionKind Kind,
        MediaSourceInfo? Result,
        StrmManifest? Manifest,
        StrmFingerprint? Previous,
        MediaSourceInfo? Source,
        ProbeWorkItem? Item)
    {
        public static ProbeAdmission Start(StrmManifest manifest, StrmFingerprint? previous, MediaSourceInfo source)
        {
            return new ProbeAdmission(ProbeAdmissionKind.Start, null, manifest, previous, source, null);
        }

        public static ProbeAdmission Delegate(MediaSourceInfo? result)
        {
            return new ProbeAdmission(ProbeAdmissionKind.Delegate, result, null, null, null, null);
        }

        public static ProbeAdmission Joined(ProbeWorkItem item)
        {
            return new ProbeAdmission(ProbeAdmissionKind.Joined, null, null, null, null, item);
        }
    }

    private enum BatchAdmissionKind
    {
        Start,
        Joined,
        Skipped,
        FirstTrust,
        NotProcessed,
        CheckStageIncomplete,
        Missing,
        Revoked
    }

    private sealed record BatchAdmission(
        BatchAdmissionKind Kind,
        StrmManifest? Manifest,
        StrmFingerprint? Previous,
        MediaSourceInfo? Source,
        ProbeWorkItem? Item)
    {
        public static BatchAdmission Start(StrmManifest manifest, StrmFingerprint? previous, MediaSourceInfo source)
        {
            return new BatchAdmission(BatchAdmissionKind.Start, manifest, previous, source, null);
        }

        public static BatchAdmission Joined(ProbeWorkItem item)
        {
            return new BatchAdmission(BatchAdmissionKind.Joined, null, null, null, item);
        }

        public static BatchAdmission Skipped()
        {
            return new BatchAdmission(BatchAdmissionKind.Skipped, null, null, null, null);
        }

        public static BatchAdmission FirstTrust()
        {
            return new BatchAdmission(BatchAdmissionKind.FirstTrust, null, null, null, null);
        }

        public static BatchAdmission NotProcessed()
        {
            return new BatchAdmission(BatchAdmissionKind.NotProcessed, null, null, null, null);
        }

        public static BatchAdmission CheckStageIncomplete()
        {
            return new BatchAdmission(BatchAdmissionKind.CheckStageIncomplete, null, null, null, null);
        }

        public static BatchAdmission Missing()
        {
            return new BatchAdmission(BatchAdmissionKind.Missing, null, null, null, null);
        }

        public static BatchAdmission Revoked()
        {
            return new BatchAdmission(BatchAdmissionKind.Revoked, null, null, null, null);
        }
    }

    private sealed class ProbeStartTracker
    {
        public bool Started { get; set; }
    }
}
