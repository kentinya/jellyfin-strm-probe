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
    private int _fingerprintStoreFailed;

    public StrmPlaybackOptimizer(
        IStrmManifestReader manifestReader,
        IProbeDecisionService decisionService,
        IStrmFingerprintRepository fingerprintRepository,
        IPlaybackSettings settings,
        ILogger<StrmPlaybackOptimizer> logger,
        ILibraryManager? libraryManager = null)
    {
        _manifestReader = manifestReader;
        _decisionService = decisionService;
        _fingerprintRepository = fingerprintRepository;
        _settings = settings;
        _logger = logger;
        _libraryManager = libraryManager;
    }

    public async Task<IReadOnlyList<MediaSourceInfo>> GetPlaybackMediaSourcesAsync(
        IMediaSourceManager native,
        BaseItem item,
        User? user,
        bool allowMediaProbe,
        bool enablePathSubstitution,
        CancellationToken cancellationToken)
    {
        if (!_settings.PlaybackAutoCheck || !allowMediaProbe || Volatile.Read(ref _fingerprintStoreFailed) != 0)
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
                cancellationToken).ConfigureAwait(false);
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
    /// </summary>
    public async Task<MediaSourceInfo?> CheckSourceAsync(
        IMediaSourceManager native,
        Guid projectItemId,
        BaseItem sourceItem,
        MediaSourceInfo source,
        string sourceKey,
        bool allowMediaProbe,
        User? user,
        bool enablePathSubstitution,
        CancellationToken cancellationToken)
    {
        var sourceId = source.Id;
        if (!allowMediaProbe)
        {
            return await GetSourceWithNativeAsync(native, sourceItem, sourceId, allowMediaProbe: false, user, enablePathSubstitution, cancellationToken)
                .ConfigureAwait(false);
        }

        if (Volatile.Read(ref _fingerprintStoreFailed) != 0)
        {
            return await GetSourceWithNativeAsync(native, sourceItem, sourceId, allowMediaProbe, user, enablePathSubstitution, cancellationToken)
                .ConfigureAwait(false);
        }

        var isStrm = IsStrm(sourceItem);
        var readResult = isStrm ? _manifestReader.Read(sourceItem.Path) : ManifestReadResult.Unsupported;
        if (readResult.Status != ManifestReadStatus.Supported || readResult.Manifest is not { } manifest)
        {
            return await GetSourceWithNativeAsync(native, sourceItem, sourceId, allowMediaProbe, user, enablePathSubstitution, cancellationToken)
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
            return await GetSourceWithNativeAsync(native, sourceItem, sourceId, allowMediaProbe, user, enablePathSubstitution, cancellationToken)
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
                return await GetSourceWithNativeAsync(native, sourceItem, sourceId, allowMediaProbe, user, enablePathSubstitution, cancellationToken)
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
                                previous).ConfigureAwait(false);
                        }
                    }
                }
                catch (Exception exception)
                {
                    MarkFingerprintStoreFailed(exception, sourceItem.Id);
                    return await GetSourceWithNativeAsync(native, sourceItem, sourceId, allowMediaProbe, user, enablePathSubstitution, cancellationToken)
                        .ConfigureAwait(false);
                }
            }

            _logger.LogInformation(
                "STRM source reused saved media information for project {ItemId}, source {SourceId}; reason {Reason}, plugin probe calls 0, Jellyfin GetMediaInfo calls observed {EncoderCallsTotal}.",
                projectItemId,
                sourceKey,
                decision.Reason,
                MediaEncoderDispatchProxy.GetMediaInfoCallCount);
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
            previous).ConfigureAwait(false);
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
        StrmFingerprint? previous)
    {
        var requiredStreamType = GetRequiredStreamType(sourceItem);
        using var probeContext = ProbeExecutionContext.Begin(projectItemId, sourceItem.Id, sourceKey, manifest.Url, requiredStreamType);
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
        try
        {
            if (_fingerprintRepository.TryCommit(candidate, previous))
            {
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
            _logger.LogWarning(
                "Native STRM probe completed for item {ItemId}, source {SourceId}, but its SQLite fingerprint write failed; matching calls {ProbeCalls}, fingerprint retained.",
                projectItemId,
                sourceKey,
                probeContext.MatchingCallCount);
        }

        return resultSource;
    }

    private async Task<MediaSourceInfo?> GetSourceWithNativeAsync(
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
}
