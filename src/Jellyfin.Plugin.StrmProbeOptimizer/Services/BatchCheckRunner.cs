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
        try
        {
            ordered = FetchCandidates(scope, counters, stopSignal);
        }
        catch (Exception exception)
        {
            result.CandidateFetchFailed = true;
            _logger.LogWarning("The batch candidate identity query failed; no media object was processed. Failure category {FailureType}.", exception.GetType().Name);
            return result;
        }

        CandidateSetFixed?.Invoke();

        if (stopSignal.IsStopped)
        {
            counters.StopRequested = 1;
            counters.Unread += ordered.Count;
            Copy(counters, ordered.Count, result, completed: false);
            return result;
        }

        for (var batchStart = 0; batchStart < ordered.Count; batchStart += BatchSize)
        {
            if (stopSignal.IsStopped || !_settings.Enabled || _optimizer.IsFingerprintStoreUnavailable)
            {
                counters.StopRequested |= stopSignal.IsStopped ? 1 : 0;
                counters.Disabled |= _settings.Enabled ? 0 : 1;
                break;
            }

            var batchIds = new Guid[Math.Min(BatchSize, ordered.Count - batchStart)];
            for (var index = 0; index < batchIds.Length; index++)
            {
                batchIds[index] = ordered[batchStart + index];
            }

            IReadOnlyList<BaseItem> items;
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

            await ProcessBatchAsync(items, batchIds, counters, stopSignal, settled =>
            {
                ReportProgress(progress, settled, ordered.Count);
            }).ConfigureAwait(false);

            if (counters.StoreUnavailable != 0 || counters.Disabled != 0)
            {
                break;
            }
        }

        var settledCount = counters.Checked + counters.NotProcessed + counters.Missing + counters.Revoked;
        var unaccounted = ordered.Count - settledCount - counters.ReadIncomplete;
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
        Copy(counters, ordered.Count, result, completed);
        if (completed)
        {
            progress.Report(100);
        }

        return result;
    }

    private IReadOnlyList<Guid> FetchCandidates(BatchLibraryScope scope, Counters counters, BatchStopSignal stopSignal)
    {
        var candidates = new List<Guid>();
        var seen = new HashSet<Guid>();
        foreach (var libraryId in scope.LibraryIds)
        {
            if (stopSignal.IsStopped || !_settings.Enabled)
            {
                break;
            }

            var ids = _candidateSource.GetLibraryCandidateIds(libraryId);
            counters.RawCandidateCount += ids.Count;
            foreach (var id in ids)
            {
                if (seen.Add(id))
                {
                    candidates.Add(id);
                }
            }
        }

        // A stable, explicit Guid order fixes the identity sequence for this run without depending on media names
        // or the native paging order.
        candidates.Sort();
        return candidates;
    }

    private async Task ProcessBatchAsync(
        IReadOnlyList<BaseItem> items,
        IReadOnlyList<Guid> batchIds,
        Counters counters,
        BatchStopSignal stopSignal,
        Action<int> onSettled)
    {
        var queue = new ConcurrentQueue<BaseItem>();
        var returned = new HashSet<Guid>();
        foreach (var item in items)
        {
            if (returned.Add(item.Id))
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

                    await ProcessCandidateAsync(item, counters, stopSignal).ConfigureAwait(false);
                    onSettled(Settled(counters));
                }
            });
        }

        await Task.WhenAll(workers).ConfigureAwait(false);
    }

    private async Task ProcessCandidateAsync(BaseItem item, Counters counters, BatchStopSignal stopSignal)
    {
        IReadOnlyList<MediaSourceInfo> sources;
        try
        {
            sources = _native.GetStaticMediaSources(item, false);
        }
        catch (Exception exception)
        {
            _logger.LogDebug("The native source read failed for one batch candidate. Failure category {FailureType}.", exception.GetType().Name);
            Interlocked.Increment(ref counters.Missing);
            return;
        }

        var source = ResolveOwnSource(item, sources);
        if (source is null)
        {
            Interlocked.Increment(ref counters.Missing);
            return;
        }

        var projectItemId = item is Video video && video.PrimaryVersionId is { } primaryVersionId
            ? primaryVersionId
            : item.Id;
        var sourceKey = item.Id.ToString("N", CultureInfo.InvariantCulture);
        try
        {
            var outcome = await _optimizer.CheckBatchSourceAsync(_native, projectItemId, item, source, sourceKey, stopSignal)
                .ConfigureAwait(false);
            CountOutcome(counters, outcome);
        }
        catch (FingerprintStoreUnavailableException)
        {
            Interlocked.Exchange(ref counters.StoreUnavailable, 1);
            Interlocked.Increment(ref counters.ProbeIncomplete);
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
        foreach (var source in sources)
        {
            if (Guid.TryParse(source.Id, out var parsed)
                && string.Equals(parsed.ToString("N", CultureInfo.InvariantCulture), ownKey, StringComparison.OrdinalIgnoreCase))
            {
                return source;
            }
        }

        return sources.Count == 1 ? sources[0] : null;
    }

    private static int Settled(Counters counters)
    {
        return Volatile.Read(ref counters.Checked)
            + Volatile.Read(ref counters.NotProcessed)
            + Volatile.Read(ref counters.Missing)
            + Volatile.Read(ref counters.Revoked);
    }

    private static void ReportProgress(IProgress<double> progress, int settled, int candidateCount)
    {
        var percentage = Math.Min(99d, 100d * settled / Math.Max(1, candidateCount));
        progress.Report(percentage);
    }

    private static void Copy(Counters counters, int candidateCount, BatchRunResult result, bool completed)
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
        public int StopRequested;
        public int StoreUnavailable;
        public int Disabled;
    }
}
