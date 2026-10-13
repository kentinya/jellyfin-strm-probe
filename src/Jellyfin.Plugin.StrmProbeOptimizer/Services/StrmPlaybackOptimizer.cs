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
    private const string SourceKey = "primary";
    private readonly IStrmManifestReader _manifestReader;
    private readonly IProbeDecisionService _decisionService;
    private readonly IStrmFingerprintRepository _fingerprintRepository;
    private readonly IPlaybackSettings _settings;
    private readonly ILogger<StrmPlaybackOptimizer> _logger;

    public StrmPlaybackOptimizer(
        IStrmManifestReader manifestReader,
        IProbeDecisionService decisionService,
        IStrmFingerprintRepository fingerprintRepository,
        IPlaybackSettings settings,
        ILogger<StrmPlaybackOptimizer> logger)
    {
        _manifestReader = manifestReader;
        _decisionService = decisionService;
        _fingerprintRepository = fingerprintRepository;
        _settings = settings;
        _logger = logger;
    }

    public async Task<IReadOnlyList<MediaSourceInfo>> GetPlaybackMediaSourcesAsync(
        IMediaSourceManager native,
        BaseItem item,
        User? user,
        bool allowMediaProbe,
        bool enablePathSubstitution,
        CancellationToken cancellationToken)
    {
        if (!_settings.PlaybackAutoCheck
            || !allowMediaProbe
            || string.IsNullOrEmpty(item.Path)
            || !item.Path.EndsWith(".strm", StringComparison.OrdinalIgnoreCase))
        {
            if (!allowMediaProbe)
            {
                _logger.LogDebug("Playback probe permission preserved for item {ItemId}; plugin probe calls 0.", item.Id);
            }

            return await native.GetPlaybackMediaSources(item, user, allowMediaProbe, enablePathSubstitution, cancellationToken)
                .ConfigureAwait(false);
        }

        var readResult = _manifestReader.Read(item.Path);
        if (readResult.Status != ManifestReadStatus.Supported || readResult.Manifest is not { } manifest)
        {
            _logger.LogDebug("STRM optimization delegated for item {ItemId}; manifest status {Status}.", item.Id, readResult.Status);
            return await native.GetPlaybackMediaSources(item, user, allowMediaProbe, enablePathSubstitution, cancellationToken)
                .ConfigureAwait(false);
        }

        var currentSources = native.GetStaticMediaSources(item, enablePathSubstitution, user);
        var currentSource = currentSources.FirstOrDefault(source => HasPrimaryStream(item, source));
        var hasPrimaryStream = currentSource is not null;
        var nativeUrl = currentSource?.Path ?? item.ShortcutPath;
        var previous = _fingerprintRepository.Get(item.Id, SourceKey);
        var decision = _decisionService.Decide(manifest, previous, hasPrimaryStream, nativeUrl);

        if (decision.Kind is ProbeDecisionKind.SkipProbe or ProbeDecisionKind.TrustExisting)
        {
            var latestManifest = _manifestReader.Read(item.Path);
            if (latestManifest.Status != ManifestReadStatus.Supported
                || latestManifest.Manifest?.ContentHash != manifest.ContentHash)
            {
                _logger.LogInformation("STRM changed during playback decision for item {ItemId}; delegating to Jellyfin.", item.Id);
                return await ProbeWithJellyfinAsync(
                    native,
                    item,
                    user,
                    enablePathSubstitution,
                    cancellationToken,
                    manifest,
                    previous,
                    hasPrimaryStream,
                    nativeUrl).ConfigureAwait(false);
            }

            if (decision.Kind == ProbeDecisionKind.TrustExisting)
            {
                var candidate = CreateFingerprint(item.Id, manifest);
                if (!_fingerprintRepository.TryCommit(candidate, expectedPrevious: null))
                {
                    var racedBaseline = _fingerprintRepository.Get(item.Id, SourceKey);
                    var racedDecision = _decisionService.Decide(manifest, racedBaseline, hasPrimaryStream, nativeUrl);
                    if (racedDecision.Kind == ProbeDecisionKind.RequireProbe)
                    {
                        return await ProbeWithJellyfinAsync(
                            native,
                            item,
                            user,
                            enablePathSubstitution,
                            cancellationToken,
                            manifest,
                            racedBaseline,
                            hasPrimaryStream,
                            nativeUrl).ConfigureAwait(false);
                    }
                }
            }

            _logger.LogInformation(
                "STRM playback reused saved media information for item {ItemId}; reason {Reason}, plugin probe calls 0.",
                item.Id,
                decision.Reason);
            return await native.GetPlaybackMediaSources(item, user, false, enablePathSubstitution, cancellationToken)
                .ConfigureAwait(false);
        }

        return await ProbeWithJellyfinAsync(
            native,
            item,
            user,
            enablePathSubstitution,
            cancellationToken,
            manifest,
            previous,
            hasPrimaryStream,
            nativeUrl).ConfigureAwait(false);
    }

    private async Task<IReadOnlyList<MediaSourceInfo>> ProbeWithJellyfinAsync(
        IMediaSourceManager native,
        BaseItem item,
        User? user,
        bool enablePathSubstitution,
        CancellationToken cancellationToken,
        StrmManifest manifest,
        StrmFingerprint? previous,
        bool hadPrimaryStream,
        string? previousNativeUrl)
    {
        var requiredStreamType = GetRequiredStreamType(item);
        using var probeContext = ProbeExecutionContext.Begin(item.Id, manifest.Url, requiredStreamType);
        IReadOnlyList<MediaSourceInfo> sources;
        try
        {
            sources = await native.GetPlaybackMediaSources(item, user, true, enablePathSubstitution, cancellationToken)
                .ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            _logger.LogInformation("Native STRM probe canceled for item {ItemId}; matching encoder calls {ProbeCalls}, fingerprint retained.", item.Id, probeContext.MatchingCallCount);
            throw;
        }
        catch (Exception)
        {
            _logger.LogWarning("Native STRM probe failed for item {ItemId}; matching encoder calls {ProbeCalls}, fingerprint retained.", item.Id, probeContext.MatchingCallCount);
            throw;
        }

        var latestRead = _manifestReader.Read(item.Path);
        var latestManifest = latestRead.Status == ManifestReadStatus.Supported ? latestRead.Manifest : null;
        var currentUrlStillMatches = latestManifest is not null && string.Equals(latestManifest.Url, manifest.Url, StringComparison.Ordinal);
        var resultSource = sources.FirstOrDefault(source => HasPrimaryStream(item, source)
            && string.Equals(source.Path, manifest.Url, StringComparison.Ordinal));
        var itemAddressMatches = string.Equals(item.ShortcutPath, manifest.Url, StringComparison.Ordinal);
        var persistedResultIsUsable = resultSource is not null && itemAddressMatches;
        var urlChanged = (previous is not null && !string.Equals(previous.UrlHash, manifest.UrlHash, StringComparison.Ordinal))
            || (previousNativeUrl is not null && !string.Equals(previousNativeUrl, manifest.Url, StringComparison.Ordinal));

        if (!currentUrlStillMatches)
        {
            throw new InvalidOperationException("The STRM changed during Jellyfin's native probe; playback must retry with the current manifest.");
        }

        if (probeContext.MatchingCallCount > 0 && probeContext.HasSuccessfulPrimaryResult && persistedResultIsUsable && currentUrlStillMatches
            && latestManifest!.ContentHash == manifest.ContentHash)
        {
            var candidate = CreateFingerprint(item.Id, manifest);
            if (_fingerprintRepository.TryCommit(candidate, previous))
            {
                _logger.LogInformation(
                    "Native probe observed for STRM item {ItemId}; calls {ProbeCalls}, saved primary stream true, fingerprint committed.",
                    item.Id,
                    probeContext.MatchingCallCount);
            }
            else
            {
                _logger.LogWarning("Native probe result was not committed for STRM item {ItemId}; the accepted baseline changed.", item.Id);
            }
        }
        else
        {
            _logger.LogInformation(
                "Native probe not accepted for STRM item {ItemId}; calls {ProbeCalls}, primary result {PrimaryResult}, saved result {SavedResult}, manifest stable {ManifestStable}.",
                item.Id,
                probeContext.MatchingCallCount,
                probeContext.HasSuccessfulPrimaryResult,
                persistedResultIsUsable,
                currentUrlStillMatches && latestManifest?.ContentHash == manifest.ContentHash);
        }

        if (!persistedResultIsUsable && !hadPrimaryStream)
        {
            throw new InvalidOperationException("Jellyfin did not save a usable media source for the current STRM address.");
        }

        if (urlChanged && (!probeContext.HasSuccessfulPrimaryResult || !persistedResultIsUsable))
        {
            throw new InvalidOperationException("Jellyfin did not prove and save a new media stream for the changed STRM address.");
        }

        if (!persistedResultIsUsable
            && previousNativeUrl is not null
            && !string.Equals(previousNativeUrl, latestManifest?.Url ?? manifest.Url, StringComparison.Ordinal))
        {
            throw new InvalidOperationException("Jellyfin did not save the current STRM address; playback cannot safely use the previous address.");
        }

        return sources;
    }

    private static StrmFingerprint CreateFingerprint(Guid itemId, StrmManifest manifest)
    {
        return new StrmFingerprint(itemId, SourceKey, manifest.UrlHash, manifest.Sha1, manifest.Size);
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

}
