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
/// Thrown from the verified matching native probe call when the current native project identity changed during
/// native preparation, before the probe actually started. The captured project/source association no longer
/// describes the object, so the native call is aborted and the candidate is settled without overwriting the old
/// baseline. It is not a probe execution cancellation: no probe actually started.
/// </summary>
public sealed class BatchIdentityChangedException : InvalidOperationException
{
    public BatchIdentityChangedException(Guid projectItemId, string sourceKey)
        : base($"The current native project identity changed before the batch probe for item {projectItemId}, source {sourceKey} started.")
    {
    }
}

/// <summary>
/// Thrown from the verified matching native probe call when the plugin was disabled during native preparation,
/// after the pre-start admission check but before the probe actually started. The native call is aborted, the old
/// baseline is preserved and the candidate is revoked; the run reports the early end instead of faking reliable
/// success, full completion or 100% progress. It is not a probe execution cancellation: no probe actually started.
/// </summary>
public sealed class BatchDisabledException : InvalidOperationException
{
    public BatchDisabledException(Guid projectItemId, string sourceKey)
        : base($"The plugin was disabled during native preparation for item {projectItemId}, source {sourceKey}; the batch probe was not started.")
    {
    }
}

/// <summary>
/// The stage at which a batch candidate observed a fingerprint store fault. A decision-stage read fault means
/// the probe decision was never reached, so the candidate is a check-stage failure. An execution-stage fault
/// means the native probe already ran and the candidate had been decided to need a probe, so it must be counted
/// as a probe-incomplete instead of being moved out of the need-probe denominator.
/// </summary>
public enum FingerprintStoreFailureStage
{
    /// <summary>The fault happened while reading the decision input, before the candidate needed a probe.</summary>
    Decision,

    /// <summary>The fault happened while executing or committing an already-required probe.</summary>
    Execution
}

/// <summary>
/// Thrown by the batch source entry when the SQLite fingerprint store has faulted. The batch stops starting
/// further work and reports the store as unavailable instead of delegating to a full-library native probe.
/// </summary>
public sealed class FingerprintStoreUnavailableException : InvalidOperationException
{
    public FingerprintStoreUnavailableException(Exception? innerException = null)
        : this(FingerprintStoreFailureStage.Decision, innerException)
    {
    }

    public FingerprintStoreUnavailableException(FingerprintStoreFailureStage stage, Exception? innerException = null)
        : base("The STRM fingerprint store is unavailable; batch optimization stopped.", innerException)
    {
        Stage = stage;
    }

    /// <summary>Gets the stage at which the store fault was observed.</summary>
    public FingerprintStoreFailureStage Stage { get; }
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
    /// Gets the <see cref="System.Diagnostics.Stopwatch.GetTimestamp"/> value captured when the stop was first
    /// confirmed, or <c>0</c> before any stop. It lets the batch measure the unavoidable delay of a synchronous
    /// native query that could not be interrupted.
    /// </summary>
    public long StoppedTimestamp { get; private set; }

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
            // Record the administrator-stop timestamp once. A disable may already have closed admission
            // without a timestamp, so a later real administrator stop must still be measured.
            if (StoppedTimestamp == 0)
            {
                StoppedTimestamp = System.Diagnostics.Stopwatch.GetTimestamp();
            }

            _stopped = 1;
        }
    }

    /// <summary>
    /// Closes admission for this run without cancelling the token or recording an administrator stop. It reuses
    /// the same latch as <see cref="ConfirmStop"/> so a reason already observed by one consumer (a mid-run
    /// disable) also stops every other already-dispatched but not-yet-started candidate of the same run, even if
    /// the plugin is re-enabled before those candidates reach their start boundary. It never cancels an already
    /// started probe, native save, verification or conditional commit, and it does not clear a later real
    /// administrator stop. The reason itself is recorded by the caller through the existing disabled counter;
    /// this latch only answers whether the run may still admit new work.
    /// </summary>
    public void CloseAdmission()
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

    /// <summary>
    /// Rolls back a start that <see cref="TryBeginProbe"/> provisionally counted but that the coordinator then
    /// rejected (a duplicate same-source start), so <see cref="StartedCount"/> never inflates the real native call count.
    /// </summary>
    public void AbortProbe()
    {
        lock (_gate)
        {
            if (_inFlight > 0)
            {
                _inFlight--;
            }

            if (_startedCount > 0)
            {
                _startedCount--;
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
