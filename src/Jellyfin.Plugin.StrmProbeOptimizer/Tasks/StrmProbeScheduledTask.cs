using Jellyfin.Plugin.StrmProbeOptimizer.Services;
using MediaBrowser.Model.Tasks;
using Microsoft.Extensions.Logging;

namespace Jellyfin.Plugin.StrmProbeOptimizer.Tasks;

/// <summary>
/// The single native Jellyfin scheduled task "STRM 媒体信息检查". Jellyfin owns discovery, manual run, stop,
/// trigger configuration and progress. The task has no default trigger; an administrator sets the schedule in the
/// native scheduled task page. It performs no playback session and never fabricates a PlaybackInfo request.
/// </summary>
public sealed class StrmProbeScheduledTask : IScheduledTask, IConfigurableScheduledTask
{
    public const string TaskKey = "StrmProbeOptimizerBatchCheck";

    private readonly BatchCheckRunner _runner;
    private readonly IPlaybackSettings _settings;
    private readonly ILogger<StrmProbeScheduledTask> _logger;

    public StrmProbeScheduledTask(
        BatchCheckRunner runner,
        IPlaybackSettings settings,
        ILogger<StrmProbeScheduledTask> logger)
    {
        _runner = runner;
        _settings = settings;
        _logger = logger;
    }

    public string Name => "STRM 媒体信息检查";

    public string Key => TaskKey;

    public string Description => "Checks the selected Jellyfin media libraries' versioned STRM sources and uses the native probe only when the current STRM or its saved media stream really changed. First checks trust the existing saved stream.";

    public string Category => "STRM Probe Optimizer";

    public bool IsHidden => false;

    public bool IsEnabled => _settings.Enabled;

    public bool IsLogged => true;

    /// <summary>
    /// Returns no default trigger so a fresh install never runs automatically. A thrown exception here would make
    /// the native worker fall back to a daily trigger, so this must always return an empty sequence.
    /// </summary>
    /// <returns>The empty default trigger sequence.</returns>
    public IEnumerable<TaskTriggerInfo> GetDefaultTriggers() => [];

    public async Task ExecuteAsync(IProgress<double> progress, CancellationToken cancellationToken)
    {
        var result = await _runner.RunAsync(progress, cancellationToken).ConfigureAwait(false);

        // The summary is always emitted, independent of DetailedLog, so failure and recovery feedback does not
        // depend on verbose logging. It carries no signed URL, token, cookie or private path.
        _logger.LogInformation(
            "STRM media information check finished: candidates {Candidates} (raw {RawCandidates}, duplicates {Duplicates}), checked {Checked}, skipped {Skipped}, first trust {FirstTrust}, need probe {NeedProbe}, reliable success {ReliableSuccess}, probe incomplete {ProbeIncomplete}, check-stage incomplete {CheckStageIncomplete}, not processed {NotProcessed}, missing {Missing}, revoked {Revoked}, read incomplete {ReadIncomplete}, unread {Unread}, actual probe calls {ActualProbeCalls}, candidate fetch {CandidateFetchMs} ms, batch read {BatchReadMs} ms, stop requested {StopRequested}, store unavailable {StoreUnavailable}, scope unavailable {ScopeUnavailable}, candidate fetch failed {CandidateFetchFailed}, disabled {Disabled}.",
            result.CandidateCount,
            result.RawCandidateCount,
            result.DuplicateIdCount,
            result.Checked,
            result.Skipped,
            result.FirstTrust,
            result.NeedProbe,
            result.ReliableSuccess,
            result.ProbeIncomplete,
            result.CheckStageIncomplete,
            result.NotProcessed,
            result.Missing,
            result.Revoked,
            result.ReadIncomplete,
            result.Unread,
            result.ActualProbeCalls,
            result.CandidateFetchMilliseconds,
            result.BatchReadMilliseconds,
            result.StopRequested,
            result.StoreUnavailable,
            result.ScopeUnavailable,
            result.CandidateFetchFailed,
            result.Disabled);

        if (result.StopRequested)
        {
            // The settlement above already waited for every started probe to save, verify and conditionally
            // commit. Only now does the task surface the native stop result, so the worker records Cancelled.
            throw new OperationCanceledException("The STRM media information check was stopped by the administrator.", cancellationToken);
        }

        if (result.StoreUnavailable)
        {
            throw new InvalidOperationException("The STRM fingerprint store is unavailable; the batch check stopped without probing the rest of the library. Repair the plugin state and run the task again.");
        }

        if (result.ScopeUnavailable)
        {
            throw new InvalidOperationException("The saved batch media library selection is invalid or references libraries that no longer exist; re-save the plugin configuration and run the task again.");
        }

        if (result.CandidateFetchFailed)
        {
            throw new InvalidOperationException("The native media library candidate query failed; no media object was processed. Run the task again.");
        }

        if (result.ReadIncomplete > 0)
        {
            throw new InvalidOperationException("The native media object batch read failed; the batch check stopped before the whole scope was processed. Run the task again.");
        }

        if (result.Disabled)
        {
            // The administrator disabled the plugin mid-run; the already started work settled and the task ended
            // early without completing the fixed candidate set.
            throw new OperationCanceledException("The STRM media information check ended early because the plugin was disabled.", cancellationToken);
        }
    }
}
