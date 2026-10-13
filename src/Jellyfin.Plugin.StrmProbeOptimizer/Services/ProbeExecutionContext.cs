using System.Threading;
using MediaBrowser.Model.Entities;
using MediaBrowser.Model.MediaInfo;

namespace Jellyfin.Plugin.StrmProbeOptimizer.Services;

public sealed class ProbeExecutionContext : IDisposable
{
    private static readonly AsyncLocal<ProbeExecutionContext?> AmbientContext = new();
    private readonly ProbeExecutionContext? _previous;
    private int _matchingCallCount;
    private int _hasPrimaryResult;
    private int _disposed;

    private ProbeExecutionContext(Guid itemId, string expectedUrl, MediaStreamType requiredStreamType)
    {
        ItemId = itemId;
        ExpectedUrl = expectedUrl;
        RequiredStreamType = requiredStreamType;
        _previous = AmbientContext.Value;
        AmbientContext.Value = this;
    }

    public Guid ItemId { get; }

    public string ExpectedUrl { get; }

    public MediaStreamType RequiredStreamType { get; }

    public int MatchingCallCount => Volatile.Read(ref _matchingCallCount);

    public bool HasSuccessfulPrimaryResult => Volatile.Read(ref _hasPrimaryResult) != 0;

    public static ProbeExecutionContext? Current => AmbientContext.Value;

    public static ProbeExecutionContext Begin(Guid itemId, string expectedUrl, MediaStreamType requiredStreamType)
    {
        return new ProbeExecutionContext(itemId, expectedUrl, requiredStreamType);
    }

    public void MarkCall(string? requestedPath)
    {
        if (!string.Equals(requestedPath, ExpectedUrl, StringComparison.Ordinal))
        {
            return;
        }

        Interlocked.Increment(ref _matchingCallCount);
    }

    public void RecordResult(string? requestedPath, MediaInfo result)
    {
        if (!string.Equals(requestedPath, ExpectedUrl, StringComparison.Ordinal))
        {
            return;
        }

        if (result.MediaStreams?.Any(stream => stream.Type == RequiredStreamType) == true)
        {
            Interlocked.Exchange(ref _hasPrimaryResult, 1);
        }
    }

    public void Dispose()
    {
        if (Interlocked.Exchange(ref _disposed, 1) == 0)
        {
            AmbientContext.Value = _previous;
        }
    }
}
