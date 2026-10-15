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
    /// Gets the measured in-memory capacity of the candidate identity structures (the ordered id list plus the
    /// de-duplication set) for this run. It is reported separately from the thread allocation counter so the O(N)
    /// identity cost is observable without claiming a constant total memory footprint.
    /// </summary>
    public long CandidateSetCapacityBytes { get; set; }

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
            Copy(counters, candidateCount: 0, result, completed: false, candidateTotalKnown: true);
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
        long candidateSetCapacityBytes = 0;
        var fetchTimer = System.Diagnostics.Stopwatch.StartNew();
        var fetchAllocatedBefore = GC.GetAllocatedBytesForCurrentThread();
        try
        {
            (ordered, candidatesComplete) = FetchCandidates(scope, counters, stopSignal, out candidateSetCapacityBytes);
        }
        catch (Exception exception)
        {
            result.CandidateFetchFailed = true;
            // A stop or disable confirmed during the synchronous query must not disappear behind the fetch
            // failure: the native task can then report both the administrator cancellation and the failure.
            counters.StopRequested |= stopSignal.IsStopped ? 1 : 0;
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
            result.CandidateSetCapacityBytes = candidateSetCapacityBytes;
        }

        CandidateSetFixed?.Invoke();

        if (!candidatesComplete)
        {
            // The candidate identity set was interrupted before every selected library was queried. The complete
            // candidate total is unknown, so no complete denominator is published and no object is processed.
            counters.StopRequested |= stopSignal.IsStopped ? 1 : 0;
            counters.Disabled |= _settings.Enabled ? 0 : 1;
            Copy(counters, candidateCount: 0, result, completed: false, candidateTotalKnown: false, candidateFetchMilliseconds: fetchMilliseconds);
            return result;
        }

        var candidateCount = ordered.Count;
        if (stopSignal.IsStopped || !_settings.Enabled)
        {
            // Every selected library was queried before the stop/disable, so the complete identity set is known.
            // Keep the real denominator and count every not-yet-read candidate as unread instead of discarding it.
            counters.StopRequested |= stopSignal.IsStopped ? 1 : 0;
            counters.Disabled |= _settings.Enabled ? 0 : 1;
            counters.Unread = candidateCount;
            Copy(counters, candidateCount, result, completed: false, candidateTotalKnown: true, candidateFetchMilliseconds: fetchMilliseconds);
            return result;
        }

        for (var batchStart = 0; batchStart < ordered.Count; batchStart += BatchSize)
        {
            if (stopSignal.IsStopped || !_settings.Enabled || _optimizer.IsFingerprintStoreUnavailable)
            {
                counters.StopRequested |= stopSignal.IsStopped ? 1 : 0;
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

        counters.StopRequested |= stopSignal.IsStopped ? 1 : 0;
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

    private (IReadOnlyList<Guid> Ordered, bool Complete) FetchCandidates(BatchLibraryScope scope, Counters counters, BatchStopSignal stopSignal, out long capacityBytes)
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

            // A synchronous native query cannot be interrupted. Re-check the stop/disable state after it returns
            // so a stop confirmed during the call never continues into the next query, object read or probe.
            if (stopSignal.IsStopped || !_settings.Enabled)
            {
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
        capacityBytes = (long)candidates.Capacity * 16 + (long)seen.Count * 24;
        return (candidates, complete);
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
                        if (stopSignal.IsStopped || !_settings.Enabled || counters.StoreUnavailable != 0)
                        {
                            if (!_settings.Enabled)
                            {
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
        public int LastProgressMilli;
        public readonly object ProgressGate = new();
        public int StopRequested;
        public int StoreUnavailable;
        public int Disabled;
    }
}
