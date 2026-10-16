using System.Collections.Concurrent;
using System.Globalization;
using Jellyfin.Plugin.StrmProbeOptimizer.Services;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Library;
using MediaBrowser.Model.Dto;
using Microsoft.Extensions.Logging;

namespace Jellyfin.Plugin.StrmProbeOptimizer.Services;

/// <summary>
/// The reconcileable result of one batch run. The counters describe the fixed candidate identity set captured for
/// this run, not a transactional snapshot of the library or the total number of supported STRM sources.
/// </summary>
public sealed class BatchRunResult
{
    public long RawCandidateCount { get; set; }

    public int CandidateCount { get; set; }

    public int Checked { get; set; }

    public int Skipped { get; set; }

    public int FirstTrust { get; set; }

    public int ReliableSuccess { get; set; }

    public int ProbeIncomplete { get; set; }

    public int CheckStageIncomplete { get; set; }

    public int NotProcessed { get; set; }

    public int Missing { get; set; }

    public int Revoked { get; set; }

    public int ReadIncomplete { get; set; }

    public int Unread { get; set; }

    /// <summary>Gets the number of raw candidate ids that were de-duplicated away from the fixed set.</summary>
    public int DuplicateIdCount { get; set; }

    /// <summary>Gets the total number of matching native probe calls that actually started during this run.</summary>
    public int ActualProbeCalls { get; set; }

    /// <summary>Gets the wall-clock time spent acquiring the native candidate identity set.</summary>
    public double CandidateFetchMilliseconds { get; set; }

    /// <summary>Gets the bytes allocated on the runner thread while acquiring, de-duplicating and sorting the candidate identity set.</summary>
    public long CandidateFetchAllocatedBytes { get; set; }

    /// <summary>
    /// Gets the sampled peak of the process managed heap observed during the candidate identity fetch (the maximum
    /// of <c>GC.GetTotalMemory(false)</c> samples taken before and after each selected-library query and after the
    /// sort), minus the pre-fetch baseline. It is a sampled process-heap peak, not an exact attribution to the
    /// identity structures; it is reported separately from the measured backing capacity and the cumulative thread
    /// allocation so the three are never conflated.
    /// </summary>
    public long CandidateFetchPeakBytes { get; set; }

    /// <summary>
    /// Gets the measured backing capacity in bytes of the candidate identity structures at the end of the fetch:
    /// the real <c>List&lt;Guid&gt;.Capacity</c> and <c>HashSet&lt;Guid&gt;.Capacity</c> (the actual allocated slot
    /// counts, including growth slack), multiplied by the documented per-slot size. Unlike the size-model estimate
    /// this is a measured figure, but it is the final backing capacity, not a sampled peak during growth.
    /// </summary>
    public long CandidateSetMeasuredCapacityBytes { get; set; }

    /// <summary>
    /// Gets the estimated in-memory size of the candidate identity structures (the ordered id list plus the
    /// de-duplication set) from the element counts, using a documented size model. It is an estimate, not a
    /// measured peak: it does not include bucket/slack capacity, growth copies or the native query's own temporary
    /// allocations. It is reported separately from the measured capacity and allocation counters so the O(N)
    /// identity cost is observable without claiming a constant total memory footprint or a measured peak.
    /// </summary>
    public long CandidateSetEstimatedBytes { get; set; }

    /// <summary>
    /// Gets the measured managed-memory delta retained after the candidate identity set was built (a
    /// <c>GC.GetTotalMemory</c> sample after the set minus one taken before the fetch). It is a measured retained
    /// figure for the fixed identity set and is reported alongside the size-model estimate.
    /// </summary>
    public long CandidateSetRetainedBytes { get; set; }

    /// <summary>
    /// Gets the measured wall-clock latency from the moment the stop was confirmed during a synchronous native
    /// query to the moment that query returned. A synchronous native query cannot be interrupted, so this is the
    /// real delay the batch observes before it can stop admission. It is <c>0</c> when no stop was confirmed during
    /// a synchronous query.
    /// </summary>
    public double StopQueryReturnLatencyMilliseconds { get; set; }

    /// <summary>
    /// Gets a value indicating whether every selected library was queried, so <see cref="CandidateCount"/> is a
    /// known complete candidate total. When <c>false</c> the identity set was interrupted and the total is unknown.
    /// </summary>
    public bool CandidateTotalKnown { get; set; }

    /// <summary>Gets the accumulated wall-clock time spent reading the native batch media objects.</summary>
    public double BatchReadMilliseconds { get; set; }

    /// <summary>Gets the number of native batch object reads performed for the fixed candidate set.</summary>
    public int BatchReadCount { get; set; }

    /// <summary>Gets the bytes allocated on the runner thread while reading the native batch media objects.</summary>
    public long BatchReadAllocatedBytes { get; set; }

    public bool StopRequested { get; set; }

    public bool StoreUnavailable { get; set; }

    public bool ScopeUnavailable { get; set; }

    public bool CandidateFetchFailed { get; set; }

    public bool Disabled { get; set; }

    public bool Completed { get; set; }

    /// <summary>Gets the number of candidates that settled during this run.</summary>
    public int Settled => Checked + NotProcessed + Missing + Revoked;

    /// <summary>Gets the number of candidates that require a probe.</summary>
    public int NeedProbe => ReliableSuccess + ProbeIncomplete;

    /// <summary>Gets the total number of incomplete candidates.</summary>
    public int Incomplete => CheckStageIncomplete + ProbeIncomplete;
}

/// <summary>
/// Runs the fixed-candidate batch check: fetch the candidate identity set once, fix it, then read and check the
/// current objects in bounded batches with a fixed consumer count. It reuses the optimizer's shared source check,
/// coordinator, native probe and conditional fingerprint commit.
/// </summary>
public sealed class BatchCheckRunner
{
    public const int BatchSize = 128;

    public const int MaxConsumers = 8;

    private readonly StrmPlaybackOptimizer _optimizer;
    private readonly IBatchScopeResolver _scopeResolver;
    private readonly IBatchCandidateSource _candidateSource;
    private readonly IMediaSourceManager _native;
    private readonly IPlaybackSettings _settings;
    private readonly ILogger<BatchCheckRunner> _logger;

    public BatchCheckRunner(
        StrmPlaybackOptimizer optimizer,
        IBatchScopeResolver scopeResolver,
        IBatchCandidateSource candidateSource,
        IMediaSourceManager native,
        IPlaybackSettings settings,
        ILogger<BatchCheckRunner> logger)
    {
        _optimizer = optimizer;
        _scopeResolver = scopeResolver;
        _candidateSource = candidateSource;
        _native = native;
        _settings = settings;
        _logger = logger;
    }

    /// <summary>
    /// Gets or sets a test-only hook invoked after the candidate identity set has been fixed and before object
    /// processing starts. It lets a deterministic regression mutate the library between the two phases.
    /// </summary>
    internal Action? CandidateSetFixed { get; set; }

    /// <summary>
    /// Gets or sets a test-only hook invoked when a fixed consumer starts and stops processing one candidate. It
    /// lets a deterministic regression observe the peak number of active consumers. It is <c>null</c> in production.
    /// </summary>
    internal Action<bool>? ConsumerActivityChanged { get; set; }

    /// <summary>
    /// Gets or sets a test-only override for the fixed consumer count. It lets a deterministic regression force a
    /// single consumer so the stop/start boundary is observable without a timing delay. It is
    /// <see cref="MaxConsumers"/> in production.
    /// </summary>
    internal int ConsumerLimit { get; set; } = MaxConsumers;

    /// <summary>
    /// Gets the number of fixed consumer tasks created so far. It is only observed by deterministic tests to prove
    /// the batch never creates one task per candidate.
    /// </summary>
    internal int ConsumerTaskCount { get; private set; }

    public async Task<BatchRunResult> RunAsync(IProgress<double> progress, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(progress);
        var counters = new Counters();
        var result = new BatchRunResult();
        using var stopSignal = new BatchStopSignal(cancellationToken);
        progress.Report(0);
        double fetchMilliseconds = 0;

        // A fingerprint store that already faulted on an earlier run stays latched off until the next restart.
        // Report it as unavailable and start no candidate fetch, read or probe.
        if (_optimizer.IsFingerprintStoreUnavailable)
        {
            counters.StoreUnavailable = 1;
            // No candidate query was issued, so the candidate total is unknown: this is distinct from a complete
            // empty library, which reports a known total of zero.
            Copy(counters, candidateCount: 0, result, completed: false, candidateTotalKnown: false);
            return result;
        }

        BatchLibraryScope scope;
        try
        {
            scope = _scopeResolver.Resolve();
        }
        catch (BatchScopeUnavailableException exception)
        {
            result.ScopeUnavailable = true;
            _logger.LogWarning("The batch media library scope is unavailable: {Reason}", exception.Message);
            return result;
        }

        IReadOnlyList<Guid> ordered;
        bool candidatesComplete;
        long candidateSetEstimatedBytes = 0;
        long candidateSetMeasuredCapacityBytes = 0;
        var fetchTimer = System.Diagnostics.Stopwatch.StartNew();
        var fetchAllocatedBefore = GC.GetAllocatedBytesForCurrentThread();
        var fetchRetainedBefore = GC.GetTotalMemory(forceFullCollection: true);
        long fetchPeakSample = fetchRetainedBefore;
        try
        {
            (ordered, candidatesComplete) = FetchCandidates(scope, counters, stopSignal, out candidateSetEstimatedBytes, out candidateSetMeasuredCapacityBytes, ref fetchPeakSample);
        }
        catch (Exception exception)
        {
            result.CandidateFetchFailed = true;
            // A stop or disable confirmed during the synchronous query must not disappear behind the fetch
            // failure: the native task can then report both the administrator cancellation and the failure.
            counters.StopRequested |= stopSignal.CancellationToken.IsCancellationRequested ? 1 : 0;
            counters.Disabled |= _settings.Enabled ? 0 : 1;
            _logger.LogWarning("The batch candidate identity query failed; no media object was processed. Failure category {FailureType}.", exception.GetType().Name);
            // Preserve the identity work already measured before the failure (partial raw ids, duplicates, time,
            // allocation and capacity) so a partial fetch is not reported as an empty, cost-free run.
            Copy(counters, candidateCount: 0, result, completed: false, candidateTotalKnown: false, candidateFetchMilliseconds: fetchMilliseconds);
            return result;
        }
        finally
        {
            fetchTimer.Stop();
            fetchMilliseconds = fetchTimer.Elapsed.TotalMilliseconds;
            result.CandidateFetchMilliseconds = fetchMilliseconds;
            result.CandidateFetchAllocatedBytes = GC.GetAllocatedBytesForCurrentThread() - fetchAllocatedBefore;
            result.CandidateSetEstimatedBytes = candidateSetEstimatedBytes;
            result.CandidateSetMeasuredCapacityBytes = candidateSetMeasuredCapacityBytes;
            result.CandidateFetchPeakBytes = Math.Max(0, fetchPeakSample - fetchRetainedBefore);
            // A measured retained-memory delta for the fixed identity set. It is sampled around the fetch with a
            // full collection so it reports retained bytes rather than the transient garbage the native query made.
            result.CandidateSetRetainedBytes = Math.Max(0, GC.GetTotalMemory(forceFullCollection: true) - fetchRetainedBefore);
            result.StopQueryReturnLatencyMilliseconds = counters.StopQueryReturnLatencyMilliseconds;
        }

        CandidateSetFixed?.Invoke();

        if (!candidatesComplete)
        {
            // The candidate identity set was interrupted before every selected library was queried. The complete
            // candidate total is unknown, so no complete denominator is published and no object is processed.
            counters.StopRequested |= stopSignal.CancellationToken.IsCancellationRequested ? 1 : 0;
            counters.Disabled |= _settings.Enabled ? 0 : 1;
            Copy(counters, candidateCount: 0, result, completed: false, candidateTotalKnown: false, candidateFetchMilliseconds: fetchMilliseconds);
            return result;
        }

        var candidateCount = ordered.Count;
        if (stopSignal.IsStopped || !_settings.Enabled)
        {
            // Every selected library was queried before the stop/disable, so the complete identity set is known.
            // Keep the real denominator and count every not-yet-read candidate as unread instead of discarding it.
            // A disable closes admission for the whole run so no already-dispatched candidate can start later.
            if (!_settings.Enabled)
            {
                stopSignal.CloseAdmission();
            }

            counters.StopRequested |= stopSignal.CancellationToken.IsCancellationRequested ? 1 : 0;
            counters.Disabled |= _settings.Enabled ? 0 : 1;
            counters.Unread = candidateCount;
            Copy(counters, candidateCount, result, completed: false, candidateTotalKnown: true, candidateFetchMilliseconds: fetchMilliseconds);
            return result;
        }

        for (var batchStart = 0; batchStart < ordered.Count; batchStart += BatchSize)
        {
            if (stopSignal.IsStopped || !_settings.Enabled || _optimizer.IsFingerprintStoreUnavailable)
            {
                if (!_settings.Enabled)
                {
                    stopSignal.CloseAdmission();
                }

                counters.StopRequested |= stopSignal.CancellationToken.IsCancellationRequested ? 1 : 0;
                counters.Disabled |= _settings.Enabled ? 0 : 1;
                counters.StoreUnavailable |= _optimizer.IsFingerprintStoreUnavailable ? 1 : 0;
                break;
            }

            var batchIds = new Guid[Math.Min(BatchSize, ordered.Count - batchStart)];
            for (var index = 0; index < batchIds.Length; index++)
            {
                batchIds[index] = ordered[batchStart + index];
            }

            IReadOnlyList<BaseItem> items;
            var readTimer = System.Diagnostics.Stopwatch.StartNew();
            var readAllocatedBefore = GC.GetAllocatedBytesForCurrentThread();
            try
            {
                items = _candidateSource.GetBatchItems(batchIds, scope.LibraryIds);
            }
            catch (Exception exception)
            {
                Interlocked.Add(ref counters.ReadIncomplete, batchIds.Length);
                _logger.LogWarning("The batch object read failed; stopping further batch work. Failure category {FailureType}.", exception.GetType().Name);
                break;
            }
            finally
            {
                readTimer.Stop();
                counters.BatchReadMilliseconds += readTimer.Elapsed.TotalMilliseconds;
                counters.BatchReadCount++;
                counters.BatchReadAllocatedBytes += GC.GetAllocatedBytesForCurrentThread() - readAllocatedBefore;
                // A synchronous native object read cannot be interrupted either; record the stop-to-return delay.
                RecordStopQueryLatency(counters, stopSignal);
            }

            await ProcessBatchAsync(items, batchIds, scope.LibraryIds, counters, stopSignal, settled =>
            {
                ReportProgress(progress, counters, settled, candidateCount);
            }).ConfigureAwait(false);

            if (counters.StoreUnavailable != 0 || counters.Disabled != 0)
            {
                break;
            }
        }

        var settledCount = counters.Checked + counters.NotProcessed + counters.Missing + counters.Revoked;
        var unaccounted = candidateCount - settledCount - counters.ReadIncomplete;
        if (unaccounted > 0)
        {
            Interlocked.Add(ref counters.Unread, unaccounted);
        }

        counters.StopRequested |= stopSignal.CancellationToken.IsCancellationRequested ? 1 : 0;
        var completed = counters.StopRequested == 0
            && counters.StoreUnavailable == 0
            && counters.Disabled == 0
            && counters.ReadIncomplete == 0
            && counters.Unread == 0;
        Copy(counters, candidateCount, result, completed, stopSignal.StartedCount, candidateFetchMilliseconds: fetchMilliseconds, candidateTotalKnown: true);
        if (completed)
        {
            progress.Report(100);
        }

        return result;
    }

    private (IReadOnlyList<Guid> Ordered, bool Complete) FetchCandidates(BatchLibraryScope scope, Counters counters, BatchStopSignal stopSignal, out long estimatedBytes, out long measuredCapacityBytes, ref long peakSample)
    {
        var candidates = new List<Guid>();
        var seen = new HashSet<Guid>();
        var complete = true;
        foreach (var libraryId in scope.LibraryIds)
        {
            if (stopSignal.IsStopped || !_settings.Enabled)
            {
                complete = false;
                break;
            }

            var ids = _candidateSource.GetLibraryCandidateIds(libraryId);
            counters.RawCandidateCount += ids.Count;
            // Sample the process managed heap after the native query returned (its temporary allocations are still
            // live) so the O(N) query cost is captured as a sampled process-heap peak.
            peakSample = Math.Max(peakSample, GC.GetTotalMemory(forceFullCollection: false));

            // A synchronous native query cannot be interrupted. Re-check the stop/disable state after it returns
            // so a stop confirmed during the call never continues into the next query, object read or probe. The
            // stop-to-return latency is measured so the unavoidable delay is disclosed instead of claimed immediate.
            if (stopSignal.IsStopped || !_settings.Enabled)
            {
                RecordStopQueryLatency(counters, stopSignal);
                complete = false;
                break;
            }

            foreach (var id in ids)
            {
                if (seen.Add(id))
                {
                    candidates.Add(id);
                }
                else
                {
                    // A repeated raw candidate id is counted separately so the identity accounting reconciles.
                    Interlocked.Increment(ref counters.DuplicateIdCount);
                }
            }
        }

        // A stable, explicit Guid order fixes the identity sequence for this run without depending on media names
        // or the native paging order.
        candidates.Sort();
        peakSample = Math.Max(peakSample, GC.GetTotalMemory(forceFullCollection: false));
        // Documented size-model estimate from the element counts. It must not be called a measured peak; the
        // measured backing capacity and the retained-memory delta are the measured figures.
        estimatedBytes = candidates.Count * 16L + seen.Count * 24L;
        // Measured backing capacity: the real List/HashSet capacities (actual allocated slots, including growth
        // slack) at the end of the fetch, multiplied by the same documented per-slot size.
        measuredCapacityBytes = candidates.Capacity * 16L + seen.Capacity * 24L;
        return (candidates, complete);
    }

    private static void RecordStopQueryLatency(Counters counters, BatchStopSignal stopSignal)
    {
        if (!stopSignal.IsStopped || stopSignal.StoppedTimestamp == 0 || counters.StopQueryReturnLatencyMilliseconds != 0)
        {
            return;
        }

        counters.StopQueryReturnLatencyMilliseconds = System.Diagnostics.Stopwatch.GetElapsedTime(stopSignal.StoppedTimestamp).TotalMilliseconds;
    }

    private async Task ProcessBatchAsync(
        IReadOnlyList<BaseItem> items,
        IReadOnlyList<Guid> batchIds,
        IReadOnlyList<Guid> scopeLibraryIds,
        Counters counters,
        BatchStopSignal stopSignal,
        Action<int> onSettled)
    {
        var queue = new ConcurrentQueue<BaseItem>();
        var requested = batchIds.ToHashSet();
        var returned = new HashSet<Guid>();
        foreach (var item in items)
        {
            // Only requested candidate ids may become work. A duplicate or an extra returned object that was not
            // part of this fixed batch is refused so it can never settle a second time or expand the scope.
            if (requested.Contains(item.Id) && returned.Add(item.Id))
            {
                queue.Enqueue(item);
            }
        }

        // Requested ids that the native query did not return are settled as missing; extra returned objects that
        // were not requested are refused and never create additional work.
        foreach (var id in batchIds)
        {
            if (!returned.Contains(id))
            {
                Interlocked.Increment(ref counters.Missing);
                onSettled(Settled(counters));
            }
        }

        var consumerCount = Math.Max(1, Math.Min(ConsumerLimit, queue.Count));
        ConsumerTaskCount += consumerCount;
        var workers = new Task[consumerCount];
        for (var index = 0; index < consumerCount; index++)
        {
            workers[index] = Task.Run(async () =>
            {
                while (queue.TryDequeue(out var item))
                {
                    ConsumerActivityChanged?.Invoke(true);
                    try
                    {
                        if (stopSignal.IsStopped || !_settings.Enabled || counters.StoreUnavailable != 0 || counters.Disabled != 0)
                        {
                            if (!_settings.Enabled)
                            {
                                // A disable observed by one consumer must close admission for the whole run, not
                                // only for the next dequeue. An already-dispatched consumer that later observes a
                                // re-enabled plugin must still be refused at its start boundary so it never adds a
                                // new probe after the reason was observed.
                                stopSignal.CloseAdmission();
                                Interlocked.Exchange(ref counters.Disabled, 1);
                            }

                            Interlocked.Increment(ref counters.Revoked);
                            onSettled(Settled(counters));
                            continue;
                        }

                        await ProcessCandidateAsync(item, scopeLibraryIds, counters, stopSignal).ConfigureAwait(false);
                        onSettled(Settled(counters));
                    }
                    finally
                    {
                        ConsumerActivityChanged?.Invoke(false);
                    }
                }
            });
        }

        await Task.WhenAll(workers).ConfigureAwait(false);
    }

    private async Task ProcessCandidateAsync(BaseItem item, IReadOnlyList<Guid> scopeLibraryIds, Counters counters, BatchStopSignal stopSignal)
    {
        // Re-read the current native object first. The candidate identity captured when the fixed set was created
        // may be stale by the time this consumer actually processes it: the native object may have been deleted,
        // changed type, moved out of the selected scope or been assigned a different primary version. The current
        // object is used for the project identity, source key and own-source resolution below.
        var current = _candidateSource.GetCurrentItem(item);
        if (current is null || current.GetType() != item.GetType())
        {
            Interlocked.Increment(ref counters.Missing);
            return;
        }

        IReadOnlyList<MediaSourceInfo> sources;
        try
        {
            sources = _native.GetStaticMediaSources(current, false);
        }
        catch (Exception exception)
        {
            _logger.LogDebug("The native source read failed for one batch candidate. Failure category {FailureType}.", exception.GetType().Name);
            Interlocked.Increment(ref counters.Missing);
            return;
        }

        var source = ResolveOwnSource(current, sources);
        if (source is null)
        {
            Interlocked.Increment(ref counters.Missing);
            return;
        }

        var projectItemId = current is Video video && video.PrimaryVersionId is { } primaryVersionId
            ? primaryVersionId
            : current.Id;
        var sourceKey = current.Id.ToString("N", CultureInfo.InvariantCulture);
        try
        {
            var outcome = await _optimizer.CheckBatchSourceAsync(_native, projectItemId, current, source, sourceKey, stopSignal, scopeLibraryIds, _candidateSource)
                .ConfigureAwait(false);
            CountOutcome(counters, outcome);
        }
        catch (BatchDisabledException)
        {
            // The plugin was disabled during native preparation, before the matching native call. No probe started,
            // the old baseline is preserved and the reservation/permit was released. Surface the exact reason so the
            // final-item summary reports the early end instead of faking reliable success, completion or 100%.
            Interlocked.Exchange(ref counters.Disabled, 1);
            Interlocked.Increment(ref counters.Revoked);
        }
        catch (FingerprintStoreUnavailableException exception)
        {
            // A global store fault is reported as unavailable and stops further batch work. The counter depends on
            // the stage: a decision-stage read fault never reached "needs probe", while an execution/commit-stage
            // fault happened after the candidate was already decided to need a probe and must stay in that denominator.
            Interlocked.Exchange(ref counters.StoreUnavailable, 1);
            if (exception.Stage == FingerprintStoreFailureStage.Execution)
            {
                Interlocked.Increment(ref counters.ProbeIncomplete);
            }
            else
            {
                Interlocked.Increment(ref counters.CheckStageIncomplete);
            }

            Interlocked.Increment(ref counters.Checked);
        }
        catch (Exception exception)
        {
            _logger.LogDebug("One batch candidate could not be checked and is reported as incomplete. Failure category {FailureType}.", exception.GetType().Name);
            Interlocked.Increment(ref counters.ProbeIncomplete);
            Interlocked.Increment(ref counters.Checked);
        }
    }

    private static void CountOutcome(Counters counters, BatchSourceOutcome outcome)
    {
        switch (outcome)
        {
            case BatchSourceOutcome.NotProcessed:
                Interlocked.Increment(ref counters.NotProcessed);
                break;
            case BatchSourceOutcome.CheckStageIncomplete:
                Interlocked.Increment(ref counters.CheckStageIncomplete);
                Interlocked.Increment(ref counters.Checked);
                break;
            case BatchSourceOutcome.Missing:
                Interlocked.Increment(ref counters.Missing);
                break;
            case BatchSourceOutcome.Skipped:
                Interlocked.Increment(ref counters.Skipped);
                Interlocked.Increment(ref counters.Checked);
                break;
            case BatchSourceOutcome.FirstTrust:
                Interlocked.Increment(ref counters.FirstTrust);
                Interlocked.Increment(ref counters.Skipped);
                Interlocked.Increment(ref counters.Checked);
                break;
            case BatchSourceOutcome.Probed:
                Interlocked.Increment(ref counters.ReliableSuccess);
                Interlocked.Increment(ref counters.Checked);
                break;
            case BatchSourceOutcome.ProbeIncomplete:
                Interlocked.Increment(ref counters.ProbeIncomplete);
                Interlocked.Increment(ref counters.Checked);
                break;
            case BatchSourceOutcome.Revoked:
                Interlocked.Increment(ref counters.Revoked);
                break;
        }
    }

    internal static MediaSourceInfo? ResolveOwnSource(BaseItem item, IReadOnlyList<MediaSourceInfo> sources)
    {
        var ownKey = item.Id.ToString("N", CultureInfo.InvariantCulture);
        return sources.FirstOrDefault(source => Guid.TryParse(source.Id, out var parsed)
            && string.Equals(parsed.ToString("N", CultureInfo.InvariantCulture), ownKey, StringComparison.OrdinalIgnoreCase));
    }

    private static int Settled(Counters counters)
    {
        return Volatile.Read(ref counters.Checked)
            + Volatile.Read(ref counters.NotProcessed)
            + Volatile.Read(ref counters.Missing)
            + Volatile.Read(ref counters.Revoked);
    }

    private static void ReportProgress(IProgress<double> progress, Counters counters, int settled, int candidateCount)
    {
        var percentage = Math.Min(99d, 100d * settled / Math.Max(1, candidateCount));
        var milli = (int)Math.Floor(percentage * 1000d);
        // Progress is monotonic even though multiple consumers report concurrently: the comparison and the actual
        // report happen under one short lock, so a late lower report can never move the native progress back and
        // the observable report order matches the reported values.
        lock (counters.ProgressGate)
        {
            if (milli <= counters.LastProgressMilli)
            {
                return;
            }

            counters.LastProgressMilli = milli;
            progress.Report(percentage);
        }
    }

    private static void Copy(Counters counters, int candidateCount, BatchRunResult result, bool completed, int actualProbeCalls = 0, double candidateFetchMilliseconds = 0, bool candidateTotalKnown = true)
    {
        result.RawCandidateCount = counters.RawCandidateCount;
        result.CandidateCount = candidateCount;
        result.Checked = counters.Checked;
        result.Skipped = counters.Skipped;
        result.FirstTrust = counters.FirstTrust;
        result.ReliableSuccess = counters.ReliableSuccess;
        result.ProbeIncomplete = counters.ProbeIncomplete;
        result.CheckStageIncomplete = counters.CheckStageIncomplete;
        result.NotProcessed = counters.NotProcessed;
        result.Missing = counters.Missing;
        result.Revoked = counters.Revoked;
        result.ReadIncomplete = counters.ReadIncomplete;
        result.Unread = counters.Unread;
        result.DuplicateIdCount = counters.DuplicateIdCount;
        result.ActualProbeCalls = actualProbeCalls;
        result.CandidateFetchMilliseconds = candidateFetchMilliseconds;
        result.CandidateTotalKnown = candidateTotalKnown;
        result.BatchReadMilliseconds = counters.BatchReadMilliseconds;
        result.BatchReadCount = counters.BatchReadCount;
        result.BatchReadAllocatedBytes = counters.BatchReadAllocatedBytes;
        result.StopQueryReturnLatencyMilliseconds = counters.StopQueryReturnLatencyMilliseconds;
        result.StopRequested = counters.StopRequested != 0;
        result.StoreUnavailable = counters.StoreUnavailable != 0;
        result.Disabled = counters.Disabled != 0;
        result.Completed = completed;
    }

    private sealed class Counters
    {
        public long RawCandidateCount;
        public int Checked;
        public int Skipped;
        public int FirstTrust;
        public int ReliableSuccess;
        public int ProbeIncomplete;
        public int CheckStageIncomplete;
        public int NotProcessed;
        public int Missing;
        public int Revoked;
        public int ReadIncomplete;
        public int Unread;
        public int DuplicateIdCount;
        public double BatchReadMilliseconds;
        public int BatchReadCount;
        public long BatchReadAllocatedBytes;
        public double StopQueryReturnLatencyMilliseconds;
        public int LastProgressMilli;
        public readonly object ProgressGate = new();
        public int StopRequested;
        public int StoreUnavailable;
        public int Disabled;
    }
}
