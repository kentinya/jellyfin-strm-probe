using System.Threading;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Model.Entities;
using MediaBrowser.Model.MediaInfo;

namespace Jellyfin.Plugin.StrmProbeOptimizer.Services;

public sealed class ProbeExecutionContext : IDisposable
{
    private static readonly AsyncLocal<ProbeExecutionContext?> AmbientContext = new();
    private readonly ProbeExecutionContext? _previous;
    private readonly object _sync = new();
    private readonly HashSet<PrimaryStreamIdentity> _successfulPrimaryResults = [];
    private readonly HashSet<PrimaryStreamIdentity> _persistedPrimaryResults = [];
    private readonly Action? _onMatchingCallStarted;
    private int _matchingCallCount;
    private int _startNotified;
    private int _hasPrimaryResult;
    private int _hasPersistedAddress;
    private int _disposed;

    private ProbeExecutionContext(Guid projectId, Guid sourceItemId, string sourceKey, string expectedUrl, MediaStreamType requiredStreamType, Action? onMatchingCallStarted)
    {
        ProjectId = projectId;
        SourceItemId = sourceItemId;
        SourceKey = sourceKey;
        ExpectedUrl = expectedUrl;
        RequiredStreamType = requiredStreamType;
        _onMatchingCallStarted = onMatchingCallStarted;
        _previous = AmbientContext.Value;
        AmbientContext.Value = this;
    }

    public Guid ProjectId { get; }

    public Guid SourceItemId { get; }

    public string SourceKey { get; }

    public string ExpectedUrl { get; }

    public MediaStreamType RequiredStreamType { get; }

    public int MatchingCallCount => Volatile.Read(ref _matchingCallCount);

    public bool HasSuccessfulPrimaryResult => Volatile.Read(ref _hasPrimaryResult) != 0;

    public bool HasPersistedPrimaryResult
    {
        get
        {
            lock (_sync)
            {
                return _persistedPrimaryResults.Count > 0;
            }
        }
    }

    public bool HasPersistedAddress => Volatile.Read(ref _hasPersistedAddress) != 0;

    public static ProbeExecutionContext? Current => AmbientContext.Value;

    public static ProbeExecutionContext Begin(Guid itemId, string expectedUrl, MediaStreamType requiredStreamType)
    {
        return Begin(itemId, itemId, itemId.ToString("N"), expectedUrl, requiredStreamType);
    }

    public static ProbeExecutionContext Begin(
        Guid projectId,
        Guid sourceItemId,
        string sourceKey,
        string expectedUrl,
        MediaStreamType requiredStreamType,
        Action? onMatchingCallStarted = null)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(sourceKey);
        return new ProbeExecutionContext(projectId, sourceItemId, sourceKey, expectedUrl, requiredStreamType, onMatchingCallStarted);
    }

    public void MarkCall(string? requestedPath)
    {
        if (!string.Equals(requestedPath, ExpectedUrl, StringComparison.Ordinal))
        {
            return;
        }

        Interlocked.Increment(ref _matchingCallCount);
        if (Interlocked.Exchange(ref _startNotified, 1) == 0)
        {
            // The verified matching native call is the real start boundary. Notify the access layer before
            // the native call proceeds so a same-source caller can join the running probe.
            _onMatchingCallStarted?.Invoke();
        }
    }

    public void RecordResult(string? requestedPath, MediaInfo result)
    {
        if (!string.Equals(requestedPath, ExpectedUrl, StringComparison.Ordinal))
        {
            return;
        }

        var primaryStream = result.MediaStreams?.FirstOrDefault(stream => stream.Type == RequiredStreamType);
        if (primaryStream is not null)
        {
            lock (_sync)
            {
                _successfulPrimaryResults.Add(PrimaryStreamIdentity.From(primaryStream));
                Interlocked.Exchange(ref _hasPrimaryResult, 1);
            }
        }
    }

    public void RecordPersistedMediaStreams(Guid itemId, IReadOnlyList<MediaStream> streams)
    {
        if (itemId != SourceItemId)
        {
            return;
        }

        var primaryStream = streams.FirstOrDefault(stream => stream.Type == RequiredStreamType);
        if (primaryStream is null)
        {
            return;
        }

        var identity = PrimaryStreamIdentity.From(primaryStream);
        lock (_sync)
        {
            if (_successfulPrimaryResults.Contains(identity))
            {
                _persistedPrimaryResults.Add(identity);
            }
        }
    }

    public bool IsPersistedProbeResult(MediaStream stream)
    {
        var identity = PrimaryStreamIdentity.From(stream);
        lock (_sync)
        {
            return _persistedPrimaryResults.Contains(identity);
        }
    }

    public void RecordPersistedItem(BaseItem item)
    {
        if (item.Id == SourceItemId && string.Equals(item.ShortcutPath, ExpectedUrl, StringComparison.Ordinal))
        {
            Interlocked.Exchange(ref _hasPersistedAddress, 1);
        }
    }

    public void Dispose()
    {
        if (Interlocked.Exchange(ref _disposed, 1) == 0)
        {
            AmbientContext.Value = _previous;
        }
    }

    private readonly record struct PrimaryStreamIdentity(
        MediaStreamType Type,
        string? Codec,
        string? CodecTag,
        string? Language,
        int? Index,
        int? Width,
        int? Height,
        int? Channels,
        int? SampleRate,
        int? BitRate,
        int? BitDepth,
        double? AverageFrameRate,
        double? RealFrameRate,
        double? ReferenceFrameRate,
        string? Profile,
        string? PixelFormat,
        string? AspectRatio,
        string? ChannelLayout,
        string? ColorRange,
        string? ColorSpace,
        string? ColorTransfer,
        string? ColorPrimaries,
        Jellyfin.Data.Enums.VideoRangeType VideoRangeType,
        string? TimeBase,
        string? CodecTimeBase,
        double? Level,
        bool? IsDefault,
        bool? IsForced,
        bool? IsHearingImpaired,
        bool? IsOriginal,
        bool? IsInterlaced,
        bool? IsAnamorphic,
        bool? IsAvc)
    {
        public static PrimaryStreamIdentity From(MediaStream stream)
        {
            return new PrimaryStreamIdentity(
                stream.Type,
                stream.Codec,
                stream.CodecTag,
                stream.Language,
                stream.Index,
                stream.Width,
                stream.Height,
                stream.Channels,
                stream.SampleRate,
                stream.BitRate,
                stream.BitDepth,
                stream.AverageFrameRate,
                stream.RealFrameRate,
                stream.ReferenceFrameRate,
                stream.Profile,
                stream.PixelFormat,
                stream.AspectRatio,
                stream.ChannelLayout,
                stream.ColorRange,
                stream.ColorSpace,
                stream.ColorTransfer,
                stream.ColorPrimaries,
                stream.VideoRangeType,
                stream.TimeBase,
                stream.CodecTimeBase,
                stream.Level,
                stream.IsDefault,
                stream.IsForced,
                stream.IsHearingImpaired,
                stream.IsOriginal,
                stream.IsInterlaced,
                stream.IsAnamorphic,
                stream.IsAVC);
        }
    }
}
