namespace Jellyfin.Plugin.StrmProbeOptimizer.Services;

/// <summary>
/// Thrown from the verified matching native probe call when the batch stop was already confirmed, so the
/// native probe must not start. It is not a probe execution cancellation; the owner settles the reservation
/// as not started and the batch reports the candidate as revoked.
/// </summary>
public sealed class BatchStopRejectedException : InvalidOperationException
{
    public BatchStopRejectedException(Guid projectItemId, string sourceKey)
        : base($"The batch check stopped before the native probe for item {projectItemId}, source {sourceKey} started.")
    {
    }
}

/// <summary>
/// Thrown by the batch source entry when the SQLite fingerprint store has faulted. The batch stops starting
/// further work and reports the store as unavailable instead of delegating to a full-library native probe.
/// </summary>
public sealed class FingerprintStoreUnavailableException : InvalidOperationException
{
    public FingerprintStoreUnavailableException(Exception? innerException = null)
        : base("The STRM fingerprint store is unavailable; batch optimization stopped.", innerException)
    {
    }
}

/// <summary>
/// The single start/stop boundary of one batch run. It makes "stop confirmed before the matching native call"
/// and "already actually started" mutually exclusive under one short lock, so exactly one of them wins the race.
/// A stop confirmed through this signal is never passed into an already started probe, native save, verification
/// or fingerprint commit.
/// </summary>
public sealed class BatchStopSignal : IDisposable
{
    private readonly object _gate = new();
    private readonly CancellationTokenRegistration _registration;
    private int _stopped;
    private int _inFlight;
    private int _startedCount;

    public BatchStopSignal(CancellationToken cancellationToken)
    {
        CancellationToken = cancellationToken;
        _registration = cancellationToken.Register(static state => ((BatchStopSignal)state!).ConfirmStop(), this);
        if (cancellationToken.IsCancellationRequested)
        {
            ConfirmStop();
        }
    }

    public CancellationToken CancellationToken { get; }

    /// <summary>Gets a value indicating whether the stop has been confirmed and no new probe may start.</summary>
    public bool IsStopped => Volatile.Read(ref _stopped) != 0;

    /// <summary>Gets the number of plugin probes whose matching native call actually started and is not yet settled.</summary>
    public int InFlight => Volatile.Read(ref _inFlight);

    /// <summary>
    /// Gets the total number of matching native probe calls that actually started during this batch run. It lets
    /// the run report the real native call count separately from the per-candidate reliable outcome counters.
    /// </summary>
    public int StartedCount => Volatile.Read(ref _startedCount);

    /// <summary>Latches the stop boundary. Idempotent and safe to call from any thread.</summary>
    public void ConfirmStop()
    {
        lock (_gate)
        {
            _stopped = 1;
        }
    }

    /// <summary>
    /// Tries to cross the actual probe start boundary. Returns <c>false</c> when the stop was already confirmed,
    /// in which case the native call must be aborted. Returns <c>true</c> and registers the probe as in flight
    /// otherwise; the caller must call <see cref="EndProbe"/> when the probe is settled.
    /// </summary>
    public bool TryBeginProbe()
    {
        lock (_gate)
        {
            if (_stopped != 0)
            {
                return false;
            }

            _inFlight++;
            _startedCount++;
            return true;
        }
    }

    /// <summary>Marks an actually started probe as settled.</summary>
    public void EndProbe()
    {
        lock (_gate)
        {
            if (_inFlight > 0)
            {
                _inFlight--;
            }
        }
    }

    /// <summary>Throws an <see cref="OperationCanceledException"/> when the stop has been confirmed.</summary>
    public void ThrowIfStopped()
    {
        if (IsStopped)
        {
            throw new OperationCanceledException("The batch check was stopped.", CancellationToken);
        }
    }

    public void Dispose()
    {
        _registration.Dispose();
    }
}

/// <summary>
/// The verified outcome of one native probe execution. It lets the access layer distinguish a reliable
/// verified-and-committed result from a result whose fingerprint write failed, without a second source of truth.
/// </summary>
public sealed record ProbeExecutionOutcome(MediaBrowser.Model.Dto.MediaSourceInfo Source, bool Committed, bool FingerprintStoreUnavailable);

/// <summary>
/// The settlement of one batch candidate after its source check. Every value maps to one counted candidate so the
/// batch statistics satisfy the documented equations.
/// </summary>
public enum BatchSourceOutcome
{
    /// <summary>The current object is not a supported versioned STRM (ordinary media, legacy or unsupported input).</summary>
    NotProcessed,

    /// <summary>The STRM carried a supported marker but its current content could not be read or parsed.</summary>
    CheckStageIncomplete,

    /// <summary>Jellyfin no longer returns the candidate object or its native source.</summary>
    Missing,

    /// <summary>The decision reused an accepted baseline without a probe.</summary>
    Skipped,

    /// <summary>The first check trusted an existing primary stream and created the baseline without a probe.</summary>
    FirstTrust,

    /// <summary>A native probe actually started, verified and committed a new fingerprint.</summary>
    Probed,

    /// <summary>A probe was required but did not produce a verified, saved and committed result.</summary>
    ProbeIncomplete,

    /// <summary>The SQLite fingerprint store faulted; the batch must stop starting further work.</summary>
    StoreUnavailable,

    /// <summary>The stop was confirmed before the matching native call; the candidate was revoked.</summary>
    Revoked
}
