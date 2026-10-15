using System.Globalization;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using Jellyfin.Plugin.StrmProbeOptimizer.Interceptors;
using Jellyfin.Plugin.StrmProbeOptimizer.Services;
using Jellyfin.Plugin.StrmProbeOptimizer.Tasks;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Entities.Audio;
using MediaBrowser.Controller.Library;
using MediaBrowser.Controller.Persistence;
using MediaBrowser.Model.Dto;
using MediaBrowser.Model.Entities;
using MediaBrowser.Model.MediaInfo;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace Jellyfin.Plugin.StrmProbeOptimizer.Tests;

[TestClass]
[TestCategory("Batch")]
public sealed class BatchCheckTests
{
    private const string ValidSha1 = "0123456789abcdef0123456789abcdef01234567";
    private const string SecondSha1 = "fedcba9876543210fedcba9876543210fedcba98";

    // ---------- Scope and candidate enumeration (AC-T2 / B03) ----------

    [TestMethod]
    public async Task BatchFixesTheCandidateSetOnceAndReadsInBoundedBatches()
    {
        using var harness = new BatchHarness();
        var a = harness.AddSupported("https://media.example.invalid/a.mp4", ValidSha1, 10);
        var b = harness.AddSupported("https://media.example.invalid/b.mp4", ValidSha1, 10);
        var c = harness.AddOrdinary("/media/ordinary.mp4");
        harness.CandidateIds = [a.Id, b.Id, c.Id, a.Id];

        var result = await harness.RunAsync();

        Assert.AreEqual(4, result.RawCandidateCount, "Every raw native id must be reported.");
        Assert.AreEqual(3, result.CandidateCount, "Duplicate candidate ids must be de-duplicated.");
        Assert.AreEqual(1, result.DuplicateIdCount, "A repeated raw candidate id must be counted as a duplicate.");
        Assert.AreEqual(1, harness.CandidateFetchCalls, "The candidate identity set must be fetched once per run.");
        Assert.AreEqual(1, harness.BatchReadCalls, "Three candidates fit into one bounded batch.");
        Assert.AreEqual(3, result.Settled, "Every fixed candidate must settle exactly once.");
        Assert.AreEqual(2, result.FirstTrust, "The two supported STRM sources with an existing stream are first-trusted.");
        Assert.AreEqual(1, result.NotProcessed, "The ordinary media object must not be probed.");
        Assert.AreEqual(0, result.ReliableSuccess);
        Assert.AreEqual(0, result.ProbeIncomplete);
        Assert.IsTrue(result.Completed);
        Assert.AreEqual(0, result.Missing);
    }

    [TestMethod]
    public async Task BatchReadsLargeCandidateSetsInFixedBatchesWithBoundedConsumers()
    {
        using var harness = new BatchHarness();
        var ids = new List<Guid>();
        for (var index = 0; index < 100_000; index++)
        {
            ids.Add(Guid.NewGuid());
        }

        harness.CandidateIds = ids;
        // Every requested candidate materializes a real complete media object. Ordinary (non-STRM) objects settle
        // as not processed without a probe, so the test measures the real batch object, consumer and activity bounds
        // for the full O(N) identity set without depending on 100k probes.
        harness.SynthesizeBatchObjects = true;
        var result = await harness.RunAsync();

        Assert.AreEqual(100_000, result.CandidateCount);
        Assert.AreEqual(100_000, result.Settled);
        Assert.AreEqual(100_000, result.NotProcessed);
        Assert.AreEqual(0, result.ReliableSuccess);
        Assert.AreEqual(0, result.ProbeIncomplete);
        Assert.IsTrue(result.Completed);
        Assert.IsTrue(harness.PeakLoadedObjects <= BatchCheckRunner.BatchSize, "No batch may load more than the fixed batch size of complete media objects.");
        var expectedBatches = (100_000 + BatchCheckRunner.BatchSize - 1) / BatchCheckRunner.BatchSize;
        Assert.IsTrue(harness.ConsumerTaskCount <= expectedBatches * BatchCheckRunner.MaxConsumers, "The batch must not create one task per candidate; consumers are bounded per batch.");
        Assert.IsTrue(harness.ConsumerTaskCount < 100_000, "The consumer task count must stay far below the candidate count.");
        Assert.IsTrue(harness.PeakActiveConsumers <= BatchCheckRunner.MaxConsumers, "The fixed consumer count must bound active work.");
        Assert.AreEqual(expectedBatches, harness.BatchReadCalls);
    }

    [TestMethod]
    public async Task BatchRechecksScopeAndSettlesObjectsThatLeftTheSelection()
    {
        using var harness = new BatchHarness();
        var kept = harness.AddSupported("https://media.example.invalid/kept.mp4", ValidSha1, 10);
        var moved = harness.AddSupported("https://media.example.invalid/moved.mp4", ValidSha1, 10);
        harness.CandidateIds = [kept.Id, moved.Id];
        // The second object is no longer inside the fixed scope when the batch read happens.
        harness.InScopeFilter = id => id != moved.Id;

        var result = await harness.RunAsync();

        Assert.AreEqual(2, result.CandidateCount);
        Assert.AreEqual(2, result.Settled);
        Assert.AreEqual(1, result.Missing, "An object that left the scope must settle as missing, not be probed.");
        Assert.AreEqual(1, result.FirstTrust);
    }

    [TestMethod]
    public async Task BatchCandidateFetchFailureStartsNoMediaProcessing()
    {
        using var harness = new BatchHarness();
        harness.AddSupported("https://media.example.invalid/a.mp4", ValidSha1, 10);
        harness.FailCandidateFetch = true;

        var result = await harness.RunAsync();

        Assert.IsTrue(result.CandidateFetchFailed);
        Assert.AreEqual(0, result.CandidateCount);
        Assert.AreEqual(0, result.Settled);
        Assert.AreEqual(0, harness.BatchReadCalls, "A failed candidate query must not start object processing.");
        Assert.AreEqual(0, harness.ProbeCalls);
        Assert.IsFalse(result.Completed);
    }

    [TestMethod]
    public async Task BatchScopeUnavailableWhenAnExplicitSelectionIsEmptyOrUnknown()
    {
        using var harness = new BatchHarness();
        harness.ScopeUnavailable = true;

        var result = await harness.RunAsync();

        Assert.IsTrue(result.ScopeUnavailable);
        Assert.AreEqual(0, result.CandidateCount);
        Assert.AreEqual(0, harness.ProbeCalls);
        Assert.IsFalse(result.Completed);
    }

    // ---------- Decision and reliable result (AC-T3 / B04 / B06) ----------

    [TestMethod]
    public async Task BatchFirstTrustCommitsWithoutProbeAndCountsAsSkipped()
    {
        using var harness = new BatchHarness();
        var item = harness.AddSupported("https://media.example.invalid/a.mp4", ValidSha1, 10);
        harness.CandidateIds = [item.Id];

        var result = await harness.RunAsync();

        Assert.AreEqual(1, result.FirstTrust);
        Assert.AreEqual(1, result.Skipped, "First trust counts as skipped.");
        Assert.AreEqual(0, result.NeedProbe);
        Assert.AreEqual(0, result.ReliableSuccess, "First trust must never be counted as a reliable probe success.");
        Assert.AreEqual(0, harness.ProbeCalls);
        Assert.IsNotNull(harness.Repository.Get(item.Id, Key(item.Id)));
    }

    [TestMethod]
    public async Task BatchUnchangedSourceSkipsWithZeroProbe()
    {
        using var harness = new BatchHarness();
        var item = harness.AddSupported("https://media.example.invalid/a.mp4", ValidSha1, 10);
        harness.CandidateIds = [item.Id];
        await harness.RunAsync();
        var probesAfterFirstRun = harness.ProbeCalls;

        var second = await harness.RunAsync();

        Assert.AreEqual(probesAfterFirstRun, harness.ProbeCalls, "An unchanged accepted source must not probe again.");
        Assert.AreEqual(1, second.Skipped);
        Assert.AreEqual(0, second.FirstTrust);
    }

    [TestMethod]
    public async Task BatchChangedUrlProbesOnceAndCountsAReliableSuccess()
    {
        using var harness = new BatchHarness();
        var item = harness.AddSupported("https://media.example.invalid/a.mp4", ValidSha1, 10);
        harness.CandidateIds = [item.Id];
        await harness.RunAsync();
        harness.WriteManifest(item, "https://media.example.invalid/a.mp4?sig=changed", ValidSha1, 10);

        var result = await harness.RunAsync();

        Assert.AreEqual(1, harness.ProbeCalls);
        Assert.AreEqual(1, result.ReliableSuccess);
        Assert.AreEqual(1, result.NeedProbe);
        Assert.AreEqual(0, result.ProbeIncomplete);
        Assert.AreEqual(1, result.Checked);
        var row = harness.Repository.Get(item.Id, Key(item.Id));
        Assert.IsNotNull(row);
        Assert.AreEqual(Hash("https://media.example.invalid/a.mp4?sig=changed"), row.UrlHash);
    }

    [TestMethod]
    public async Task BatchProbeFailureCountsIncompleteAndKeepsTheTrustedBaseline()
    {
        using var harness = new BatchHarness();
        var item = harness.AddSupported("https://media.example.invalid/a.mp4", ValidSha1, 10);
        harness.CandidateIds = [item.Id];
        await harness.RunAsync();
        var baseline = harness.Repository.Get(item.Id, Key(item.Id));
        harness.WriteManifest(item, "https://media.example.invalid/a.mp4?sig=changed", SecondSha1, 99);
        harness.FailItemIds.Add(item.Id);

        var result = await harness.RunAsync();

        Assert.AreEqual(1, result.ProbeIncomplete);
        Assert.AreEqual(0, result.ReliableSuccess);
        Assert.AreEqual(1, result.NeedProbe);
        Assert.AreEqual(1, result.Incomplete);
        Assert.AreEqual(baseline, harness.Repository.Get(item.Id, Key(item.Id)), "A failed probe must retain the trusted baseline.");
    }

    [TestMethod]
    public async Task BatchManifestChangeDuringDecisionDoesNotPublishAStaleFirstTrust()
    {
        using var harness = new BatchHarness();
        var item = harness.AddSupported("https://media.example.invalid/a.mp4", ValidSha1, 10);
        harness.CandidateIds = [item.Id];
        harness.OnBatchDecision = () => harness.WriteManifest(item, "https://media.example.invalid/a.mp4?sig=changed", ValidSha1, 10);

        var result = await harness.RunAsync();

        Assert.AreEqual(0, result.FirstTrust, "A STRM that changed during the decision must not publish a stale first trust.");
        Assert.IsNull(harness.Repository.Get(item.Id, Key(item.Id)));
        Assert.AreEqual(1, result.Incomplete);
    }

    [TestMethod]
    public async Task BatchMultiVersionUsesTheStableProjectAndSourceIdentity()
    {
        using var harness = new BatchHarness();
        var primary = harness.AddSupported("https://media.example.invalid/primary.mp4", ValidSha1, 10);
        var alternate = harness.AddSupported("https://media.example.invalid/alternate.mp4", ValidSha1, 10);
        alternate.PrimaryVersionId = primary.Id;
        harness.CandidateIds = [primary.Id, alternate.Id];

        var result = await harness.RunAsync();

        Assert.AreEqual(2, result.FirstTrust);
        var primaryRow = harness.Repository.Get(primary.Id, Key(primary.Id));
        var alternateRow = harness.Repository.Get(primary.Id, Key(alternate.Id));
        Assert.IsNotNull(primaryRow);
        Assert.IsNotNull(alternateRow, "The alternate version must use the primary version as its project identity.");
        Assert.IsNull(harness.Repository.Get(alternate.Id, Key(alternate.Id)), "The alternate must not be stored under its own project identity.");
    }

    [TestMethod]
    public async Task BatchAudioSourceRequiresItsOwnPrimaryStreamType()
    {
        using var harness = new BatchHarness();
        var item = harness.AddSupportedAudio("https://media.example.invalid/audio.mp3", ValidSha1, 10);
        harness.CandidateIds = [item.Id];

        var result = await harness.RunAsync();

        Assert.AreEqual(1, result.FirstTrust, "An audio STRM with an existing audio primary stream is first-trusted.");
    }

    // ---------- Mixed sharing (AC-T4) ----------

    [TestMethod]
    public async Task BatchJoinsAnAlreadyRunningSameSourceProbe()
    {
        using var harness = new BatchHarness();
        var item = harness.AddSupported("https://media.example.invalid/a.mp4", ValidSha1, 10);
        harness.CandidateIds = [item.Id];
        await harness.RunAsync();
        harness.WriteManifest(item, "https://media.example.invalid/a.mp4?sig=changed", ValidSha1, 10);

        // A real playback entry point starts the matching native probe, blocks inside it, then the batch joins.
        harness.BlockProbe = true;
        harness.AfterProbeStart = () => harness.ProbeStarted.TrySetResult();
        harness.CreateRunner();
        var native = harness.ReviewerNative!;
        var source = native.GetStaticMediaSources(item, false)[0];
        var playback = harness.ReviewerOptimizer!.CheckSourceAsync(native, item.Id, item, source, Key(item.Id), true, null, false, CancellationToken.None, true);
        await harness.ProbeStarted.Task.WaitAsync(TimeSpan.FromSeconds(10));

        var run = harness.RunAsync();
        await harness.WaitForSharedJoinAsync().WaitAsync(TimeSpan.FromSeconds(10));
        harness.ReleaseProbe.TrySetResult();
        await playback.WaitAsync(TimeSpan.FromSeconds(10));
        var result = await run.WaitAsync(TimeSpan.FromSeconds(10));

        Assert.AreEqual(1, harness.StartedProbes, "Only one matching native probe may actually start.");
        Assert.AreEqual(1, result.ReliableSuccess, "A same-source probe that actually ran and committed this version must count as this run's reliable success, not as skipped.");
        Assert.AreEqual(0, result.Skipped, "A shared committed result must not be counted as skipped.");
        Assert.AreEqual(0, harness.Coordinator.RunningCount);
        Assert.AreEqual(0, harness.Coordinator.ActivePermits);
    }

    [TestMethod]
    public async Task BatchStoppedWhileJoinedToARunningProbeStillWaitsForItsSettlement()
    {
        using var harness = new BatchHarness();
        var item = harness.AddSupported("https://media.example.invalid/a.mp4", ValidSha1, 10);
        harness.CandidateIds = [item.Id];
        await harness.RunAsync();
        harness.WriteManifest(item, "https://media.example.invalid/a.mp4?new", ValidSha1, 10);
        var coordinator = harness.Coordinator;
        var owner = await coordinator.AcquireAsync(item.Id, Key(item.Id), "hash", CancellationToken.None);
        Assert.IsTrue(coordinator.TryMarkStarted(owner.Item, out _));
        using var stop = new CancellationTokenSource();
        var run = harness.RunAsync(stop.Token);
        await harness.WaitForSharedJoinAsync().WaitAsync(TimeSpan.FromSeconds(10));
        stop.Cancel();

        // The batch must not return while the joined running probe is still executing; the batch stop never
        // cancels an already started probe.
        var early = false;
        try
        {
            await run.WaitAsync(TimeSpan.FromSeconds(1));
            early = true;
        }
        catch (TimeoutException)
        {
            early = false;
        }

        Assert.IsFalse(early, "The batch returned while the joined running probe was still executing.");
        Assert.AreEqual(1, coordinator.RunningCount, "The joined probe must still be running until it settles.");

        // Settle the joined probe and confirm the batch now returns and releases all resources.
        coordinator.Complete(owner.Item, new MediaSourceInfo { Path = item.ShortcutPath });
        var result = await run.WaitAsync(TimeSpan.FromSeconds(10));
        Assert.AreEqual(0, coordinator.RunningCount);
        Assert.AreEqual(0, coordinator.ActivePermits);
        Assert.IsTrue(result.StopRequested);
    }

    [TestMethod]
    public async Task BatchRefusesExtraReturnedObjectsThatWereNotRequested()
    {
        using var harness = new BatchHarness();
        var requested = harness.AddSupported("https://media.example.invalid/requested.mp4", ValidSha1, 10);
        var extra = harness.AddSupported("https://media.example.invalid/extra.mp4", ValidSha1, 10);
        harness.CandidateIds = [requested.Id];
        harness.ReturnExtraObjects = true;

        var result = await harness.RunAsync();

        Assert.AreEqual(result.CandidateCount, result.Settled, "One requested candidate must not settle two objects.");
        Assert.AreEqual(1, result.CandidateCount);
        Assert.IsNull(harness.Repository.Get(extra.Id, Key(extra.Id)), "An extra object that was not requested must never become work.");
    }

    [TestMethod]
    public async Task BatchRechecksScopeAtAdmissionAndSettlesObjectsThatLeftTheSelection()
    {
        using var harness = new BatchHarness();
        var kept = harness.AddSupported("https://media.example.invalid/kept.mp4", ValidSha1, 10);
        var moved = harness.AddSupported("https://media.example.invalid/moved.mp4", ValidSha1, 10);
        harness.CandidateIds = [kept.Id, moved.Id];
        await harness.RunAsync();
        // Both already have a baseline; move the second one out of the selection after the candidate set is fixed.
        harness.WriteManifest(kept, "https://media.example.invalid/kept.mp4?sig=new", ValidSha1, 10);
        harness.WriteManifest(moved, "https://media.example.invalid/moved.mp4?sig=new", ValidSha1, 10);
        harness.InScopeOverride = id => id != moved.Id;

        var result = await harness.RunAsync();

        Assert.AreEqual(1, result.ReliableSuccess, "The in-scope changed source must still be probed.");
        Assert.AreEqual(1, result.Missing, "An object that left the selected scope must settle as missing without probing.");
        Assert.AreEqual(1, harness.ProbeCalls, "Only the in-scope source may be probed.");
    }

    [TestMethod]
    public async Task BatchAlreadyUnavailableStoreReportsUnavailableWithoutFetchingCandidates()
    {
        using var harness = new BatchHarness();
        var item = harness.AddSupported("https://media.example.invalid/a.mp4", ValidSha1, 10);
        harness.CandidateIds = [item.Id];
        harness.Repository = new FaultInjectingRepository { FailGetAfter = 0 };
        var runner = harness.CreateRunner();
        var first = await runner.RunAsync(new Progress<double>(), CancellationToken.None);
        Assert.IsTrue(first.StoreUnavailable);

        var second = await runner.RunAsync(new Progress<double>(), CancellationToken.None);

        Assert.IsTrue(second.StoreUnavailable, "A latched fingerprint store failure must stay reported as unavailable.");
        Assert.AreEqual(0, second.Unread, "An already unavailable store must not invent unread candidates.");
        Assert.IsFalse(second.Completed);
    }

    [TestMethod]
    public async Task BatchStopDuringIdFetchDoesNotInventACompleteCandidateTotal()
    {
        using var harness = new BatchHarness();
        var item = harness.AddSupported("https://media.example.invalid/a.mp4", ValidSha1, 10);
        harness.CandidateIds = [item.Id];
        harness.ScopeLibraryCount = 2;
        using var stop = new CancellationTokenSource();
        harness.AfterCandidateFetch = stop.Cancel;

        var result = await harness.RunAsync(stop.Token);

        Assert.AreEqual(1, harness.CandidateFetchCalls, "The interrupted fetch must stop before the second library query.");
        Assert.IsTrue(result.StopRequested);
        Assert.AreEqual(0, result.CandidateCount, "An interrupted first-library fetch is only a partial ID set; the complete candidate total is unknown.");
        Assert.AreEqual(0, harness.ProbeCalls);
        Assert.IsFalse(result.Completed);
    }

    [TestMethod]
    public async Task BatchReportsMonotonicProgressUnderConcurrentConsumers()
    {
        using var harness = new BatchHarness();
        var items = new List<Video>();
        for (var index = 0; index < 40; index++)
        {
            items.Add(harness.AddSupported($"https://media.example.invalid/{index}.mp4", ValidSha1, 10));
        }

        harness.CandidateIds = items.Select(item => item.Id).ToList();
        var reported = new List<double>();
        var progress = new SynchronousProgress(value =>
        {
            lock (reported)
            {
                reported.Add(value);
            }
        });

        await harness.RunWithProgressAsync(progress, CancellationToken.None);

        lock (reported)
        {
            for (var index = 1; index < reported.Count; index++)
            {
                Assert.IsTrue(reported[index] >= reported[index - 1], $"Progress must be monotonic: {reported[index - 1]} then {reported[index]}.");
            }
        }
    }

    // ---------- Stop boundary and resource settlement (AC-T5) ----------

    [TestMethod]
    public async Task BatchStopRevokesNotStartedCandidatesAndSettlesStartedProbes()
    {
        using var harness = new BatchHarness();
        var first = harness.AddSupported("https://media.example.invalid/a.mp4", ValidSha1, 10);
        var second = harness.AddSupported("https://media.example.invalid/b.mp4", ValidSha1, 10);
        harness.CandidateIds = [first.Id, second.Id];
        await harness.RunAsync();
        var secondBaseline = harness.Repository.Get(second.Id, Key(second.Id));
        harness.WriteManifest(first, "https://media.example.invalid/a.mp4?sig=changed", ValidSha1, 10);
        harness.WriteManifest(second, "https://media.example.invalid/b.mp4?sig=changed", ValidSha1, 10);
        harness.ConsumerLimit = 1;
        using var stop = new CancellationTokenSource();
        harness.AfterProbeStart = () =>
        {
            harness.ProbeStarted.TrySetResult();
            stop.Cancel();
        };
        harness.BlockProbe = true;

        var run = harness.RunAsync(stop.Token);
        await harness.ProbeStarted.Task.WaitAsync(TimeSpan.FromSeconds(10));
        harness.ReleaseProbe.TrySetResult();
        var result = await run.WaitAsync(TimeSpan.FromSeconds(10));
        Assert.IsTrue(result.StopRequested);
        Assert.AreEqual(1, result.ReliableSuccess, "An already started probe must still finish and commit.");
        Assert.AreEqual(1, result.Revoked, "The candidate that never started must be revoked.");
        Assert.AreEqual(0, harness.Coordinator.RunningCount);
        Assert.AreEqual(0, harness.Coordinator.ActivePermits);
        Assert.IsFalse(result.Completed);
        Assert.IsNotNull(harness.Repository.Get(first.Id, Key(first.Id)));
        Assert.AreEqual(secondBaseline, harness.Repository.Get(second.Id, Key(second.Id)), "The revoked candidate must keep its previous baseline.");
    }

    [TestMethod]
    public async Task BatchStopConfirmedBeforeTheMatchingNativeCallDoesNotStartTheProbe()
    {
        using var harness = new BatchHarness();
        var item = harness.AddSupported("https://media.example.invalid/a.mp4", ValidSha1, 10);
        harness.CandidateIds = [item.Id];
        await harness.RunAsync();
        harness.WriteManifest(item, "https://media.example.invalid/a.mp4?sig=changed", ValidSha1, 10);
        using var stop = new CancellationTokenSource();
        harness.BeforeProbeStart = stop.Cancel;

        var result = await harness.RunAsync(stop.Token);

        Assert.IsTrue(result.StopRequested);
        Assert.AreEqual(0, harness.StartedProbes, "A stop confirmed before the matching native call must abort it.");
        Assert.AreEqual(1, result.Revoked);
        Assert.AreEqual(0, harness.Coordinator.RunningCount);
        Assert.AreEqual(0, harness.Coordinator.ActivePermits);
        Assert.IsFalse(result.Completed);
    }

    [TestMethod]
    public async Task BatchStopAndStartRaceIsDecidedAtOneBoundary()
    {
        using var harness = new BatchHarness();
        var item = harness.AddSupported("https://media.example.invalid/a.mp4", ValidSha1, 10);
        harness.CandidateIds = [item.Id];
        await harness.RunAsync();
        harness.WriteManifest(item, "https://media.example.invalid/a.mp4?sig=changed", ValidSha1, 10);
        using var stop = new CancellationTokenSource();
        // Confirm the stop exactly after the matching native call started: the start must win and still commit.
        harness.AfterProbeStart = stop.Cancel;

        var result = await harness.RunAsync(stop.Token);

        Assert.AreEqual(1, harness.StartedProbes, "When the start wins the race the probe must actually execute.");
        Assert.AreEqual(1, result.ReliableSuccess);
        Assert.AreEqual(0, result.Revoked);
        Assert.IsNotNull(harness.Repository.Get(item.Id, Key(item.Id)));
    }

    // ---------- Global failure (AC-T6) ----------

    [TestMethod]
    public async Task BatchStoreFailureStopsFurtherWorkAndReportsUnavailable()
    {
        using var harness = new BatchHarness();
        var first = harness.AddSupported("https://media.example.invalid/a.mp4", ValidSha1, 10);
        var second = harness.AddSupported("https://media.example.invalid/b.mp4", ValidSha1, 10);
        harness.CandidateIds = [first.Id, second.Id];
        harness.Repository = new FaultInjectingRepository { FailGetAfter = 1 };

        var result = await harness.RunAsync();

        Assert.IsTrue(result.StoreUnavailable);
        Assert.AreEqual(0, harness.ProbeCalls, "A fingerprint store fault must stop the batch instead of probing the rest of the library.");
        Assert.IsFalse(result.Completed);
        Assert.AreEqual(0, harness.Coordinator.RunningCount, "A store fault must not leak a running registration.");
        Assert.AreEqual(0, harness.Coordinator.PreparingCount, "A store fault during admission must release the reservation.");
        Assert.AreEqual(0, harness.Coordinator.ActivePermits, "A store fault must not leak a global permit.");
    }

    [TestMethod]
    public async Task BatchStoreFailureDuringAdmissionReleasesTheReservationAndPermit()
    {
        using var harness = new BatchHarness();
        var item = harness.AddSupported("https://media.example.invalid/a.mp4", ValidSha1, 10);
        harness.CandidateIds = [item.Id];
        await harness.RunAsync();
        harness.WriteManifest(item, "https://media.example.invalid/a.mp4?sig=changed", ValidSha1, 10);
        // The first read returns the trusted baseline, so the candidate acquires a reservation; the admission
        // re-read then faults and must release both the reservation and the global permit.
        harness.Repository = new FaultInjectingRepository(harness.Repository) { FailGetAfter = 1 };

        var result = await harness.RunAsync();

        Assert.IsTrue(result.StoreUnavailable);
        Assert.AreEqual(0, harness.ProbeCalls);
        Assert.AreEqual(0, harness.Coordinator.RunningCount);
        Assert.AreEqual(0, harness.Coordinator.PreparingCount);
        Assert.AreEqual(0, harness.Coordinator.ActivePermits);
    }

    [TestMethod]
    public async Task BatchReadFailureStopsFurtherWorkAndReportsUnread()
    {
        using var harness = new BatchHarness();
        var item = harness.AddSupported("https://media.example.invalid/a.mp4", ValidSha1, 10);
        harness.CandidateIds = [item.Id];
        harness.FailBatchRead = true;

        var result = await harness.RunAsync();

        Assert.AreEqual(1, result.ReadIncomplete);
        Assert.AreEqual(0, result.Unread);
        Assert.AreEqual(0, harness.ProbeCalls);
        Assert.IsFalse(result.Completed);
    }

    // ---------- Statistics (AC-T7) ----------

    [TestMethod]
    public async Task BatchStatisticsSatisfyTheDocumentedEquations()
    {
        using var harness = new BatchHarness();
        var trusted = harness.AddSupported("https://media.example.invalid/trusted.mp4", ValidSha1, 10);
        var changed = harness.AddSupported("https://media.example.invalid/changed.mp4", ValidSha1, 10);
        var failed = harness.AddSupported("https://media.example.invalid/failed.mp4", ValidSha1, 10);
        var ordinary = harness.AddOrdinary("/media/ordinary.mp4");
        var legacy = harness.AddLegacy("https://media.example.invalid/legacy.mp4");
        harness.CandidateIds = [trusted.Id, changed.Id, failed.Id, ordinary.Id, legacy.Id];
        await harness.RunAsync();
        harness.WriteManifest(changed, "https://media.example.invalid/changed.mp4?sig=new", ValidSha1, 10);
        harness.WriteManifest(failed, "https://media.example.invalid/failed.mp4?sig=new", SecondSha1, 99);
        harness.FailItemIds.Add(failed.Id);

        var result = await harness.RunAsync();

        Assert.AreEqual(result.Checked, result.Skipped + result.NeedProbe + result.CheckStageIncomplete, "checked = skipped + need probe + check-stage incomplete");
        Assert.AreEqual(result.NeedProbe, result.ReliableSuccess + result.ProbeIncomplete, "need probe = reliable success + probe incomplete");
        Assert.AreEqual(result.Incomplete, result.CheckStageIncomplete + result.ProbeIncomplete, "incomplete = check-stage incomplete + probe incomplete");
        Assert.AreEqual(result.CandidateCount, result.Settled + result.Unread, "candidate = settled + unread");
        Assert.AreEqual(1, result.ReliableSuccess);
        Assert.AreEqual(1, result.ProbeIncomplete);
        Assert.AreEqual(1, result.Skipped);
        Assert.AreEqual(2, result.NotProcessed, "Ordinary and legacy inputs are not processed.");
        Assert.AreEqual(0, result.FirstTrust);
        Assert.AreEqual(2, result.ActualProbeCalls, "The reliable success and the failed probe must each count one actual native call.");
        Assert.IsTrue(result.CandidateFetchMilliseconds >= 0, "The candidate fetch cost must be reported.");
        Assert.IsTrue(result.BatchReadMilliseconds >= 0, "The batch object read cost must be reported.");
    }

    // ---------- Native task surface (AC-T1 / RO-1 / RO-7 backend) ----------

    [TestMethod]
    public void ScheduledTaskExposesTheExpectedNativeIdentityAndNoDefaultTrigger()
    {
        using var harness = new BatchHarness();
        var task = harness.CreateTask();

        Assert.AreEqual("STRM 媒体信息检查", task.Name);
        Assert.AreEqual(StrmProbeScheduledTask.TaskKey, task.Key);
        Assert.IsFalse(task.IsHidden);
        Assert.IsTrue(task.IsEnabled);
        Assert.IsTrue(task.IsLogged);
        Assert.AreEqual(0, task.GetDefaultTriggers().Count(), "The task must have no default trigger so a fresh install never runs automatically.");
    }

    [TestMethod]
    public async Task ScheduledTaskReportsCancelledWhenTheRunWasStopped()
    {
        using var harness = new BatchHarness();
        var item = harness.AddSupported("https://media.example.invalid/a.mp4", ValidSha1, 10);
        harness.CandidateIds = [item.Id];
        using var stop = new CancellationTokenSource();
        stop.Cancel();
        var task = harness.CreateTask();

        await AssertThrowsAsync<OperationCanceledException>(() => task.ExecuteAsync(new Progress<double>(), stop.Token));
    }

    [TestMethod]
    public async Task ScheduledTaskReportsStoreUnavailableAsAFailure()
    {
        using var harness = new BatchHarness();
        var item = harness.AddSupported("https://media.example.invalid/a.mp4", ValidSha1, 10);
        harness.CandidateIds = [item.Id];
        harness.Repository = new FaultInjectingRepository { FailGetAfter = 0 };
        var task = harness.CreateTask();

        await AssertThrowsAsync<InvalidOperationException>(() => task.ExecuteAsync(new Progress<double>(), CancellationToken.None));
    }

    // ---------- Configuration (RO-7 backend) ----------

    [TestMethod]
    public void BatchScopeDefaultsToAllLibrariesAndLegacyConfigurationKeepsIt()
    {
        var configuration = new PluginConfiguration();
        Assert.IsTrue(configuration.BatchAllLibraries);
        Assert.AreEqual(string.Empty, configuration.BatchLibraryIds);
        Assert.IsNull(PluginConfiguration.Validate(configuration));
    }

    [TestMethod]
    public void ExplicitBatchScopeRejectsEmptyOrMalformedSelections()
    {
        var empty = new PluginConfiguration { BatchAllLibraries = false, BatchLibraryIds = string.Empty };
        Assert.IsNotNull(PluginConfiguration.Validate(empty), "An empty explicit selection must be rejected, not widened to all libraries.");

        var malformed = new PluginConfiguration { BatchAllLibraries = false, BatchLibraryIds = "not-a-guid" };
        Assert.IsNotNull(PluginConfiguration.Validate(malformed));

        var valid = new PluginConfiguration { BatchAllLibraries = false, BatchLibraryIds = $"{Guid.NewGuid():D},{Guid.NewGuid():D}" };
        Assert.IsNull(PluginConfiguration.Validate(valid));
    }

    [TestMethod]
    public void ExplicitBatchScopeParsesAStableOrderedDeDuplicatedSet()
    {
        var first = Guid.NewGuid();
        var second = Guid.NewGuid();
        var value = $"{second:D}, {first:D},{second:D}";

        Assert.IsTrue(PluginConfiguration.TryParseLibraryIds(value, out var parsed));
        CollectionAssert.AreEqual(new[] { second, first }, parsed.ToArray());
    }

    [TestMethod]
    public async Task BatchJoinedRunningProbeFailureSettlesAsProbeIncompleteWithoutRetry()
    {
        using var harness = new BatchHarness();
        var item = harness.AddSupported("https://media.example.invalid/a.mp4", ValidSha1, 10);
        harness.CandidateIds = [item.Id];
        await harness.RunAsync();
        harness.WriteManifest(item, "https://media.example.invalid/a.mp4?new", ValidSha1, 10);
        var currentHash = new StrmManifestReader().Read(item.Path).Manifest!.ContentHash;
        var owner = await harness.Coordinator.AcquireAsync(item.Id, Key(item.Id), currentHash, CancellationToken.None);
        Assert.IsTrue(harness.Coordinator.TryMarkStarted(owner.Item, out _));

        var batch = harness.RunAsync();
        await harness.WaitForSharedJoinAsync().WaitAsync(TimeSpan.FromSeconds(10));
        harness.Coordinator.Fail(owner.Item, new IOException("Controlled shared probe failure."));
        var result = await batch.WaitAsync(TimeSpan.FromSeconds(10));

        Assert.AreEqual(0, harness.StartedProbes, "A same-version shared failure must not be retried within the same round.");
        Assert.AreEqual(1, result.ProbeIncomplete, "A joined running failure must settle as probe incomplete.");
        Assert.AreEqual(0, result.Revoked);
        Assert.AreEqual(0, result.ReliableSuccess);
    }

    [TestMethod]
    public async Task BatchStoppedJoinedRunningProbeFailureCountsProbeIncomplete()
    {
        using var harness = new BatchHarness();
        var item = harness.AddSupported("https://media.example.invalid/a.mp4", ValidSha1, 10);
        harness.CandidateIds = [item.Id];
        await harness.RunAsync();
        harness.WriteManifest(item, "https://media.example.invalid/a.mp4?new", ValidSha1, 10);
        var currentHash = new StrmManifestReader().Read(item.Path).Manifest!.ContentHash;
        var owner = await harness.Coordinator.AcquireAsync(item.Id, Key(item.Id), currentHash, CancellationToken.None);
        Assert.IsTrue(harness.Coordinator.TryMarkStarted(owner.Item, out _));
        using var stop = new CancellationTokenSource();
        var batch = harness.RunAsync(stop.Token);
        await harness.WaitForSharedJoinAsync().WaitAsync(TimeSpan.FromSeconds(10));
        stop.Cancel();
        harness.Coordinator.Fail(owner.Item, new IOException("Controlled shared probe failure."));
        var result = await batch.WaitAsync(TimeSpan.FromSeconds(10));

        Assert.AreEqual(1, result.ProbeIncomplete, "A stopped joined running failure must count as probe incomplete, not revoked.");
        Assert.AreEqual(0, result.Revoked);
    }

    [TestMethod]
    public async Task BatchCommitFailureAfterActualProbeCountsProbeIncomplete()
    {
        using var harness = new BatchHarness();
        var item = harness.AddSupported("https://media.example.invalid/a.mp4", ValidSha1, 10);
        harness.CandidateIds = [item.Id];
        await harness.RunAsync();
        harness.WriteManifest(item, "https://media.example.invalid/a.mp4?new", ValidSha1, 10);
        harness.Repository = new FaultInjectingRepository(harness.Repository) { FailGetAfter = int.MaxValue, FailCommit = true };

        var result = await harness.RunAsync();

        Assert.AreEqual(1, harness.StartedProbes);
        Assert.IsTrue(result.StoreUnavailable);
        Assert.AreEqual(1, result.ProbeIncomplete, "A post-probe commit fault must stay in the need-probe denominator.");
        Assert.AreEqual(0, result.CheckStageIncomplete);
        Assert.AreEqual(0, result.ReliableSuccess);
    }

    [TestMethod]
    public async Task BatchStopAfterCompleteFixedSetKeepsTheKnownCandidateTotal()
    {
        using var harness = new BatchHarness();
        var item = harness.AddSupported("https://media.example.invalid/a.mp4", ValidSha1, 10);
        harness.CandidateIds = [item.Id];
        using var stop = new CancellationTokenSource();
        harness.AfterFixedSet = stop.Cancel;

        var result = await harness.RunAsync(stop.Token);

        Assert.IsTrue(result.StopRequested);
        Assert.AreEqual(1, result.CandidateCount, "Every id was captured before the stop; the complete denominator must not be discarded.");
        Assert.AreEqual(1, result.Unread, "The not-yet-read candidate must be counted as unread.");
        Assert.AreEqual(0, harness.ProbeCalls);
    }

    [TestMethod]
    public async Task BatchConcurrentFetchFailureAndStopKeepsTheStopReason()
    {
        using var harness = new BatchHarness();
        harness.CandidateIds = [Guid.NewGuid()];
        harness.FailCandidateFetch = true;
        using var stop = new CancellationTokenSource();
        harness.BeforeCandidateFetch = stop.Cancel;

        var result = await harness.RunAsync(stop.Token);

        Assert.IsTrue(result.CandidateFetchFailed);
        Assert.IsTrue(result.StopRequested, "A confirmed administrator stop must not disappear on the fetch-error return.");
    }

    [TestMethod]
    public async Task BatchMismatchedSingleSourceIsNotClaimedAsTheOwnSource()
    {
        using var harness = new BatchHarness();
        var item = harness.AddSupported("https://media.example.invalid/a.mp4", ValidSha1, 10);
        harness.CandidateIds = [item.Id];
        harness.SourceIdOverride = Guid.NewGuid().ToString("N");

        var result = await harness.RunAsync();

        Assert.AreEqual(0, result.FirstTrust, "A single source keyed by another owner's id must not establish this item's baseline.");
        Assert.IsNull(harness.Repository.Get(item.Id, Key(item.Id)));
        Assert.AreEqual(1, result.Missing, "A candidate whose own source cannot be identified must settle as missing.");
        Assert.AreEqual(0, harness.ProbeCalls);
    }

    [TestMethod]
    public void NativeCandidateSourceRechecksTheCurrentObjectAgainstTheScope()
    {
        var libraryA = Guid.NewGuid();
        var libraryB = Guid.NewGuid();
        var item = new Video { Id = Guid.NewGuid(), Path = "/media/a.mp4" };
        var manager = ScopeLibraryManager.Create(item, libraryA);
        var source = new LibraryBatchCandidateSource(manager.Interface);

        Assert.IsTrue(source.IsInScope(item, [libraryA]), "A current object still in the selected library must stay in scope.");
        Assert.IsFalse(source.IsInScope(item, [libraryB]), "An object moved to another library must leave the scope.");

        // The native object is deleted after the candidate set was fixed: admission must refuse it.
        manager.Current = null;
        Assert.IsFalse(source.IsInScope(item, [libraryA]), "A deleted candidate must not remain in scope.");

        // The native object changed type after the candidate set was fixed: admission must refuse it.
        manager.Current = new MediaBrowser.Controller.Entities.Audio.Audio { Id = item.Id, Path = item.Path };
        Assert.IsFalse(source.IsInScope(item, [libraryA]), "A candidate that changed type must not remain in scope.");

        // The native object was re-pointed to a different primary version: the captured project identity, source
        // key and coordination key no longer describe it, so admission must refuse it.
        manager.Current = new Video { Id = item.Id, Path = item.Path, PrimaryVersionId = Guid.NewGuid() };
        Assert.IsFalse(source.IsInScope(item, [libraryA]), "A candidate re-pointed to another primary version must not remain in scope.");
    }

    [TestMethod]
    public async Task BatchUsesTheCurrentProjectIdentityAfterTheObjectIsReRead()
    {
        using var harness = new BatchHarness();
        var item = harness.AddSupported("https://media.example.invalid/a.mp4", ValidSha1, 10);
        harness.CandidateIds = [item.Id];
        var newProject = Guid.NewGuid();
        // The current native object keeps the same id and type but now belongs to another primary version. The
        // runner must commit the baseline under the current project, never under the stale captured one.
        harness.CurrentItemOverride = _ => new Video { Id = item.Id, Path = item.Path, ShortcutPath = item.ShortcutPath, IsShortcut = true, PrimaryVersionId = newProject };

        var result = await harness.RunAsync();

        Assert.AreEqual(1, result.FirstTrust);
        Assert.IsNotNull(harness.Repository.Get(newProject, Key(item.Id)), "The current project identity must be used after the object is re-read.");
        Assert.IsNull(harness.Repository.Get(item.Id, Key(item.Id)), "The stale captured project identity must not receive the baseline.");
    }

    [TestMethod]
    public async Task BatchJoinedRunningUncommittedResultSettlesProbeIncompleteWithoutRetry()
    {
        using var harness = new BatchHarness();
        var item = harness.AddSupported("https://media.example.invalid/a.mp4", ValidSha1, 10);
        harness.CandidateIds = [item.Id];
        await harness.RunAsync();
        harness.WriteManifest(item, "https://media.example.invalid/a.mp4?new", ValidSha1, 10);
        var currentHash = new StrmManifestReader().Read(item.Path).Manifest!.ContentHash;
        var owner = await harness.Coordinator.AcquireAsync(item.Id, Key(item.Id), currentHash, CancellationToken.None);
        Assert.IsTrue(harness.Coordinator.TryMarkStarted(owner.Item, out _));

        var batch = harness.RunAsync();
        await harness.WaitForSharedJoinAsync().WaitAsync(TimeSpan.FromSeconds(10));
        // The joined owner actually ran and saved but conditionally refused the commit (the baseline changed or the
        // write failed). This round already consumed the shared execution, so it must settle as probe incomplete
        // instead of retrying within the same round or counting a reliable success.
        harness.Coordinator.Complete(owner.Item, new MediaSourceInfo { Id = Key(item.Id), Path = item.ShortcutPath }, committed: false);
        var result = await batch.WaitAsync(TimeSpan.FromSeconds(10));

        Assert.AreEqual(0, harness.StartedProbes, "A joined non-commit must not trigger a same-round retry.");
        Assert.AreEqual(1, result.ProbeIncomplete, "A joined uncommitted execution must settle as probe incomplete.");
        Assert.AreEqual(0, result.ReliableSuccess);
        Assert.AreEqual(0, result.Revoked);
    }

    [TestMethod]
    public async Task BatchStoppedJoinedRunningUncommittedResultCountsProbeIncomplete()
    {
        using var harness = new BatchHarness();
        var item = harness.AddSupported("https://media.example.invalid/a.mp4", ValidSha1, 10);
        harness.CandidateIds = [item.Id];
        await harness.RunAsync();
        harness.WriteManifest(item, "https://media.example.invalid/a.mp4?new", ValidSha1, 10);
        var currentHash = new StrmManifestReader().Read(item.Path).Manifest!.ContentHash;
        var owner = await harness.Coordinator.AcquireAsync(item.Id, Key(item.Id), currentHash, CancellationToken.None);
        Assert.IsTrue(harness.Coordinator.TryMarkStarted(owner.Item, out _));
        using var stop = new CancellationTokenSource();
        var batch = harness.RunAsync(stop.Token);
        await harness.WaitForSharedJoinAsync().WaitAsync(TimeSpan.FromSeconds(10));
        stop.Cancel();
        harness.Coordinator.Complete(owner.Item, new MediaSourceInfo { Id = Key(item.Id), Path = item.ShortcutPath }, committed: false);
        var result = await batch.WaitAsync(TimeSpan.FromSeconds(10));

        Assert.AreEqual(1, result.ProbeIncomplete, "A stopped joined uncommitted execution must count as probe incomplete, not revoked.");
        Assert.AreEqual(0, result.Revoked);
    }

    [TestMethod]
    public async Task BatchJoinedRunningChangedManifestStillSettlesWithoutRetry()
    {
        using var harness = new BatchHarness();
        var item = harness.AddSupported("https://media.example.invalid/a.mp4", ValidSha1, 10);
        harness.CandidateIds = [item.Id];
        await harness.RunAsync();
        harness.WriteManifest(item, "https://media.example.invalid/a.mp4?version2", ValidSha1, 10);
        var currentHash = new StrmManifestReader().Read(item.Path).Manifest!.ContentHash;
        var owner = await harness.Coordinator.AcquireAsync(item.Id, Key(item.Id), currentHash, CancellationToken.None);
        Assert.IsTrue(harness.Coordinator.TryMarkStarted(owner.Item, out _));

        var batch = harness.RunAsync();
        await harness.WaitForSharedJoinAsync().WaitAsync(TimeSpan.FromSeconds(10));
        // The STRM changed again while the joined execution was running, so the owner does not commit. The batch
        // must settle this round's joined execution as incomplete rather than starting another probe immediately.
        harness.WriteManifest(item, "https://media.example.invalid/a.mp4?version3", ValidSha1, 10);
        harness.Coordinator.Complete(owner.Item, new MediaSourceInfo { Id = Key(item.Id), Path = "https://media.example.invalid/a.mp4?version2" }, committed: false);
        var result = await batch.WaitAsync(TimeSpan.FromSeconds(10));

        Assert.AreEqual(0, harness.StartedProbes, "A manifest change after joining must not trigger a new probe within the same round.");
        Assert.AreEqual(1, result.ProbeIncomplete);
    }

    [TestMethod]
    public async Task BatchPartialFetchFailureRetainsAlreadyFetchedRawIds()
    {
        using var harness = new BatchHarness();
        harness.CandidateIds = [Guid.NewGuid()];
        harness.ScopeLibraryCount = 2;
        harness.BeforeCandidateFetch = () =>
        {
            if (harness.CandidateFetchCalls == 2)
            {
                harness.FailCandidateFetch = true;
            }
        };

        var result = await harness.RunAsync();

        Assert.IsTrue(result.CandidateFetchFailed);
        Assert.AreEqual(1L, result.RawCandidateCount, "The first native query returned one id before the second query failed; that raw count must be retained.");
        Assert.IsFalse(result.CandidateTotalKnown, "A partial fetch must not publish a complete candidate total.");
        Assert.AreEqual(0, harness.BatchReadCalls);
    }

    [TestMethod]
    public async Task BatchInterruptedFetchReportsUnknownTotalAndKeepsFetchCost()
    {
        using var harness = new BatchHarness();
        var item = harness.AddSupported("https://media.example.invalid/a.mp4", ValidSha1, 10);
        harness.CandidateIds = [item.Id];
        harness.ScopeLibraryCount = 2;
        using var stop = new CancellationTokenSource();
        harness.AfterCandidateFetch = stop.Cancel;

        var result = await harness.RunAsync(stop.Token);

        Assert.IsTrue(result.StopRequested);
        Assert.AreEqual(0, result.CandidateCount, "An interrupted first-library fetch is only a partial id set; the complete candidate total is unknown.");
        Assert.IsFalse(result.CandidateTotalKnown, "The result must mark the candidate total as unknown.");
        Assert.AreEqual(0, harness.ProbeCalls);
    }

    [TestMethod]
    public async Task BatchReportsCandidateSetCapacityForTheFixedIdentitySet()
    {
        using var harness = new BatchHarness();
        var ids = new List<Guid>();
        for (var index = 0; index < 2000; index++)
        {
            ids.Add(Guid.NewGuid());
        }

        harness.CandidateIds = ids;
        harness.SynthesizeBatchObjects = true;

        var result = await harness.RunAsync();

        Assert.AreEqual(2000, result.CandidateCount);
        Assert.IsTrue(result.CandidateSetCapacityBytes > 0, "The O(N) candidate identity capacity must be measured and reported.");
        Assert.IsTrue(result.CandidateFetchMilliseconds >= 0, "The candidate fetch cost must be reported.");
        Assert.IsTrue(result.CandidateTotalKnown, "A complete fetch reports a known total.");
    }

    [TestMethod]
    public async Task BatchStopConfirmedDuringSynchronousObjectReadDoesNotStartWork()
    {
        using var harness = new BatchHarness();
        var item = harness.AddSupported("https://media.example.invalid/a.mp4", ValidSha1, 10);
        harness.CandidateIds = [item.Id];
        await harness.RunAsync();
        harness.WriteManifest(item, "https://media.example.invalid/a.mp4?sig=changed", ValidSha1, 10);
        using var stop = new CancellationTokenSource();
        // A synchronous native object query cannot be interrupted. The stop is confirmed while it is in flight, and
        // the runner must not continue into a probe after the read returns.
        harness.DuringBatchRead = stop.Cancel;

        var result = await harness.RunAsync(stop.Token);

        Assert.IsTrue(result.StopRequested);
        Assert.AreEqual(0, harness.ProbeCalls, "A stop confirmed during the object read must not start a probe afterwards.");
        Assert.AreEqual(0, harness.StartedProbes);
        Assert.IsFalse(result.Completed);
    }

    [TestMethod]
    public async Task BatchStopWhileWaitingForAPermitRevokesWithoutStarting()
    {
        using var harness = new BatchHarness();
        // Two different sources with a single global permit: the first starts and blocks, the second waits.
        var first = harness.AddSupported("https://media.example.invalid/a.mp4", ValidSha1, 10);
        var second = harness.AddSupported("https://media.example.invalid/b.mp4", ValidSha1, 10);
        harness.CandidateIds = [first.Id, second.Id];
        await harness.RunAsync();
        harness.WriteManifest(first, "https://media.example.invalid/a.mp4?sig=changed", ValidSha1, 10);
        harness.WriteManifest(second, "https://media.example.invalid/b.mp4?sig=changed", ValidSha1, 10);
        using var coordinator = new ProbeCoordinator(1);
        harness.ReplaceCoordinator(coordinator);
        harness.BlockProbe = true;
        using var stop = new CancellationTokenSource();
        harness.AfterProbeStart = () =>
        {
            harness.ProbeStarted.TrySetResult();
            stop.Cancel();
        };

        var run = harness.RunAsync(stop.Token);
        await harness.ProbeStarted.Task.WaitAsync(TimeSpan.FromSeconds(10));
        harness.ReleaseProbe.TrySetResult();
        var result = await run.WaitAsync(TimeSpan.FromSeconds(10));

        Assert.IsTrue(result.StopRequested);
        Assert.AreEqual(1, result.ReliableSuccess, "The already started probe must still finish and commit.");
        Assert.AreEqual(1, result.Revoked, "The source waiting for a permit must be revoked without starting.");
        Assert.AreEqual(1, harness.StartedProbes, "Only the source that actually started may probe.");
    }

    [TestMethod]
    public void BatchStopSignalAbortRollsBackAProvisionalStartCount()
    {
        using var signal = new BatchStopSignal(CancellationToken.None);
        Assert.IsTrue(signal.TryBeginProbe(), "A probe may start before any stop is confirmed.");
        Assert.AreEqual(1, signal.StartedCount);
        Assert.AreEqual(1, signal.InFlight);

        // A coordinator-rejected duplicate start must not leave the reported real native call count inflated.
        signal.AbortProbe();
        Assert.AreEqual(0, signal.StartedCount, "An aborted provisional start must not inflate the actual probe call count.");
        Assert.AreEqual(0, signal.InFlight);

        Assert.IsTrue(signal.TryBeginProbe(), "A real start after an aborted provisional start must still be counted.");
        Assert.AreEqual(1, signal.StartedCount);
    }

    // ---------- Helpers ----------

    private static string Key(Guid id) => id.ToString("N", CultureInfo.InvariantCulture);

    /// <summary>
    /// A synchronous <see cref="IProgress{T}"/> that invokes the callback inline. The framework <see cref="Progress{T}"/>
    /// posts callbacks asynchronously, so it cannot deterministically observe the published order under concurrent
    /// consumers; this inline implementation records the exact report order.
    /// </summary>
    private sealed class SynchronousProgress : IProgress<double>
    {
        private readonly Action<double> _callback;

        public SynchronousProgress(Action<double> callback)
        {
            _callback = callback;
        }

        public void Report(double value) => _callback(value);
    }

    private static string Hash(string value) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();

    private static async Task<TException> AssertThrowsAsync<TException>(Func<Task> action)
        where TException : Exception
    {
        try
        {
            await action();
        }
        catch (TException exception)
        {
            return exception;
        }

        throw new AssertFailedException($"Expected {typeof(TException).Name}.");
    }

    private sealed class BatchHarness : IDisposable
    {
        private readonly List<BaseItem> _items = [];
        private readonly Dictionary<Guid, string> _paths = [];
        private readonly List<BatchCheckRunner> _runners = [];

        public BatchHarness()
        {
            Repository = new InMemoryStrmFingerprintRepository();
            Coordinator = new ProbeCoordinator(4);
        }

        public IStrmFingerprintRepository Repository { get; set; }

        public ProbeCoordinator Coordinator { get; private set; }

        /// <summary>Replaces the coordinator with one that has a different global limit for a focused test.</summary>
        public void ReplaceCoordinator(ProbeCoordinator coordinator)
        {
            Coordinator = coordinator;
        }

        public List<Guid> CandidateIds { get; set; } = [];

        public int CandidateFetchCalls { get; private set; }

        public int BatchReadCalls { get; private set; }

        public int PeakLoadedObjects { get; private set; }

        public int ConsumerTaskCount { get; private set; }

        public int ProbeCalls { get; private set; }

        public int StartedProbes { get; private set; }

        public bool ScopeUnavailable { get; set; }

        public bool FailCandidateFetch { get; set; }

        public bool FailBatchRead { get; set; }

        /// <summary>Gets or sets a test-only hook invoked while a synchronous native object read is in flight.</summary>
        public Action? DuringBatchRead { get; set; }

        public bool ReturnExtraObjects { get; set; }

        public bool SynthesizeBatchObjects { get; set; }

        public int PeakActiveConsumers { get; private set; }

        private int _activeConsumers;

        public int ScopeLibraryCount { get; set; } = 1;

        public Action? AfterCandidateFetch { get; set; }

        public Action? AfterFixedSet { get; set; }

        public Action? BeforeCandidateFetch { get; set; }

        public string? SourceIdOverride { get; set; }

        public Func<Guid, bool>? InScopeOverride { get; set; }

        /// <summary>Gets or sets a test-only override for the current native object re-read at admission.</summary>
        public Func<BaseItem, BaseItem?>? CurrentItemOverride { get; set; }

        public IMediaSourceManager? ReviewerNative { get; private set; }

        public StrmPlaybackOptimizer? ReviewerOptimizer { get; private set; }

        public Func<Guid, bool>? InScopeFilter { get; set; }

        public bool BlockProbe { get; set; }

        public HashSet<Guid> FailItemIds { get; } = [];

        public Action? OnStaticSourceRead { get; set; }

        public Action? OnBatchDecision { get; set; }

        public Action? BeforeProbeStart { get; set; }

        public Action? AfterProbeStart { get; set; }

        public TaskCompletionSource ProbeStarted { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

        public TaskCompletionSource ReleaseProbe { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

        private TaskCompletionSource SharedJoinReached { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

        public int ConsumerLimit { get; set; } = BatchCheckRunner.MaxConsumers;

        public Video AddSupported(string url, string? sha1, long? size)
        {
            var path = TempPath();
            WriteManifest(path, url, sha1, size);
            var item = new Video { Id = Guid.NewGuid(), Path = path, ShortcutPath = url, IsShortcut = true };
            _items.Add(item);
            _paths[item.Id] = path;
            return item;
        }

        public Video AddLegacy(string url)
        {
            var path = TempPath();
            File.WriteAllText(path, url + "\n", Encoding.UTF8);
            var item = new Video { Id = Guid.NewGuid(), Path = path, ShortcutPath = url, IsShortcut = true };
            _items.Add(item);
            _paths[item.Id] = path;
            return item;
        }

        public Video AddOrdinary(string path)
        {
            var item = new Video { Id = Guid.NewGuid(), Path = path };
            _items.Add(item);
            return item;
        }

        public Audio AddSupportedAudio(string url, string? sha1, long? size)
        {
            var path = TempPath();
            WriteManifest(path, url, sha1, size);
            var item = new Audio { Id = Guid.NewGuid(), Path = path, ShortcutPath = url, IsShortcut = true };
            _items.Add(item);
            _paths[item.Id] = path;
            return item;
        }

        public void WriteManifest(BaseItem item, string url, string? sha1, long? size)
        {
            WriteManifest(_paths[item.Id], url, sha1, size);
            item.ShortcutPath = url;
        }

        public StrmProbeScheduledTask CreateTask()
        {
            var runner = CreateRunner();
            return new StrmProbeScheduledTask(runner, new Settings(), NullLogger<StrmProbeScheduledTask>.Instance);
        }

        public Task<BatchRunResult> RunAsync(CancellationToken cancellationToken = default)
        {
            var runner = CreateRunner();
            return runner.RunAsync(new Progress<double>(), cancellationToken);
        }

        public Task<BatchRunResult> RunWithProgressAsync(IProgress<double> progress, CancellationToken cancellationToken)
        {
            var runner = CreateRunner();
            return runner.RunAsync(progress, cancellationToken);
        }

        public Task WaitForSharedJoinAsync() => SharedJoinReached.Task;

        public BatchCheckRunner CreateRunner()
        {
            var native = PlaybackOptimizerTests.ScriptedManager.Create();
            native.StaticSourceResolver = (item, _) =>
            {
                OnStaticSourceRead?.Invoke();
                var streamType = item is Audio ? MediaStreamType.Audio : MediaStreamType.Video;
                return
                [
                    new MediaSourceInfo
                    {
                        Id = SourceIdOverride ?? item.Id.ToString("N", CultureInfo.InvariantCulture),
                        Path = item.ShortcutPath,
                        MediaStreams = [new MediaStream { Type = streamType, Codec = "h264" }]
                    }
                ];
            };
            native.Playback = async (item, _, _, _) =>
            {
                ProbeCalls++;
                BeforeProbeStart?.Invoke();
                var url = item.ShortcutPath;
                var result = new MediaInfo { MediaStreams = [new MediaStream { Type = item is Audio ? MediaStreamType.Audio : MediaStreamType.Video, Codec = "h264" }] };
                var context = ProbeExecutionContext.Current!;
                context.MarkCall(url);
                StartedProbes++;
                AfterProbeStart?.Invoke();
                if (BlockProbe)
                {
                    await ReleaseProbe.Task;
                }

                if (FailItemIds.Contains(item.Id))
                {
                    throw new IOException("Injected probe failure.");
                }

                context.RecordResult(url, result);
                var streamRepository = ProbePersistenceDispatchProxy.Create(PlaybackOptimizerTests.NativePersistence.Create<IMediaStreamRepository>());
                streamRepository.SaveMediaStreams(item.Id, result.MediaStreams, CancellationToken.None);
                var itemPersistence = ProbePersistenceDispatchProxy.Create(PlaybackOptimizerTests.NativePersistence.Create<IItemPersistenceService>());
                itemPersistence.SaveItems([item], CancellationToken.None);
                return
                [
                    new MediaSourceInfo
                    {
                        Id = item.Id.ToString("N", CultureInfo.InvariantCulture),
                        Path = url,
                        MediaStreams = result.MediaStreams
                    }
                ];
            };
            var optimizer = new StrmPlaybackOptimizer(
                new StrmManifestReader(),
                new ProbeDecisionService(),
                Repository,
                new Settings(),
                NullLogger<StrmPlaybackOptimizer>.Instance,
                null,
                Coordinator)
            {
                SharedJoinBarrier = () => SharedJoinReached.TrySetResult(),
                BatchSharedJoinBarrier = () => SharedJoinReached.TrySetResult(),
                BatchDecisionBarrier = () => OnBatchDecision?.Invoke()
            };
            ReviewerNative = native.Interface;
            ReviewerOptimizer = optimizer;
            var runner = new BatchCheckRunner(
                optimizer,
                new FakeScopeResolver(this),
                new FakeCandidateSource(this),
                native.Interface,
                new Settings(),
                NullLogger<BatchCheckRunner>.Instance)
            {
                CandidateSetFixed = () => AfterFixedSet?.Invoke(),
                ConsumerLimit = ConsumerLimit,
                ConsumerActivityChanged = active =>
                {
                    if (active)
                    {
                        var current = Interlocked.Increment(ref _activeConsumers);
                        PeakActiveConsumers = Math.Max(PeakActiveConsumers, current);
                    }
                    else
                    {
                        Interlocked.Decrement(ref _activeConsumers);
                    }
                }
            };
            _runners.Add(runner);
            return runner;
        }

        internal IReadOnlyList<Guid> FetchCandidates()
        {
            CandidateFetchCalls++;
            BeforeCandidateFetch?.Invoke();
            if (FailCandidateFetch)
            {
                throw new IOException("Injected candidate fetch failure.");
            }

            AfterCandidateFetch?.Invoke();
            return CandidateIds;
        }

        internal IReadOnlyList<BaseItem> ReadBatch(IReadOnlyList<Guid> ids)
        {
            BatchReadCalls++;
            DuringBatchRead?.Invoke();
            if (FailBatchRead)
            {
                throw new IOException("Injected batch read failure.");
            }

            if (SynthesizeBatchObjects)
            {
                // Materialize one real complete object per requested id so the large-set test measures the actual
                // batch object, consumer and activity bounds instead of only the missing-id settlement path.
                var synthesized = ids
                    .Where(id => InScopeFilter is null || InScopeFilter(id))
                    .Select(id => (BaseItem)new Video { Id = id, Path = "/media/synthetic-" + id.ToString("N", CultureInfo.InvariantCulture) + ".mp4" })
                    .ToList();
                PeakLoadedObjects = Math.Max(PeakLoadedObjects, synthesized.Count);
                ConsumerTaskCount += Math.Max(1, Math.Min(ConsumerLimit, synthesized.Count));
                return synthesized;
            }

            var requested = ids.ToHashSet();
            var result = new List<BaseItem>();
            foreach (var item in _items)
            {
                if (!requested.Contains(item.Id) && !ReturnExtraObjects)
                {
                    continue;
                }

                if (InScopeFilter is not null && !InScopeFilter(item.Id))
                {
                    continue;
                }

                result.Add(item);
            }

            PeakLoadedObjects = Math.Max(PeakLoadedObjects, result.Count);
            ConsumerTaskCount += Math.Max(1, Math.Min(ConsumerLimit, result.Count));
            return result;
        }

        private static string TempPath()
        {
            return Path.Combine(Path.GetTempPath(), $"strm-probe-batch-{Guid.NewGuid():N}.strm");
        }

        private static void WriteManifest(string path, string url, string? sha1, long? size)
        {
            var lines = new List<string> { "# strm-probe-version:1" };
            if (sha1 is not null)
            {
                lines.Add("# strm-probe-sha1:" + sha1);
            }

            if (size.HasValue)
            {
                lines.Add("# strm-probe-size:" + size.Value.ToString(CultureInfo.InvariantCulture));
            }

            lines.Add(url);
            File.WriteAllText(path, string.Join('\n', lines) + "\n", Encoding.UTF8);
        }

        public void Dispose()
        {
            foreach (var path in _paths.Values)
            {
                File.Delete(path);
            }

            Coordinator.Dispose();
        }

        private sealed class Settings : IPlaybackSettings
        {
            public bool Enabled => true;

            public bool PlaybackAutoCheck => true;

            public bool DetailedLog => false;

            public int MaxConcurrentProbes => 4;

            public bool BatchAllLibraries => true;

            public string BatchLibraryIds => string.Empty;
        }

        private sealed class FakeScopeResolver : IBatchScopeResolver
        {
            private readonly BatchHarness _harness;

            public FakeScopeResolver(BatchHarness harness)
            {
                _harness = harness;
            }

            public BatchLibraryScope Resolve()
            {
                if (_harness.ScopeUnavailable)
                {
                    throw new BatchScopeUnavailableException("Injected scope failure.");
                }

                return new BatchLibraryScope(true, Enumerable.Range(0, _harness.ScopeLibraryCount).Select(_ => Guid.NewGuid()).ToArray());
            }
        }

        private sealed class FakeCandidateSource : IBatchCandidateSource
        {
            private readonly BatchHarness _harness;

            public FakeCandidateSource(BatchHarness harness)
            {
                _harness = harness;
            }

            public IReadOnlyList<Guid> GetLibraryCandidateIds(Guid libraryId) => _harness.FetchCandidates();

            public IReadOnlyList<BaseItem> GetBatchItems(IReadOnlyList<Guid> ids, IReadOnlyList<Guid> scopeLibraryIds) => _harness.ReadBatch(ids);

            public bool IsInScope(BaseItem item, IReadOnlyList<Guid> scopeLibraryIds)
            {
                return _harness.InScopeOverride?.Invoke(item.Id) ?? true;
            }

            public BaseItem? GetCurrentItem(BaseItem item) => _harness.CurrentItemOverride?.Invoke(item) ?? item;
        }
    }

    private class ScopeLibraryManager : DispatchProxy
    {
        public BaseItem? Current { get; set; }

        public Guid FolderId { get; set; }

        public ILibraryManager Interface { get; private set; } = null!;

        public static ScopeLibraryManager Create(BaseItem? current, Guid folderId)
        {
            var proxy = DispatchProxy.Create<ILibraryManager, ScopeLibraryManager>();
            var lookup = (ScopeLibraryManager)(object)proxy;
            lookup.Interface = proxy;
            lookup.Current = current;
            lookup.FolderId = folderId;
            return lookup;
        }

        protected override object? Invoke(MethodInfo? targetMethod, object?[]? args)
        {
            if (targetMethod?.Name.StartsWith(nameof(ILibraryManager.GetItemById), StringComparison.Ordinal) == true)
            {
                return Current;
            }

            if (targetMethod?.Name == nameof(ILibraryManager.GetCollectionFolders))
            {
                return new List<Folder> { new Folder { Id = FolderId } };
            }

            return targetMethod?.ReturnType == typeof(void)
                ? null
                : targetMethod?.ReturnType.IsValueType == true
                    ? Activator.CreateInstance(targetMethod.ReturnType)
                    : null;
        }
    }

    private sealed class FaultInjectingRepository : IStrmFingerprintRepository
    {
        private readonly IStrmFingerprintRepository _inner;
        private int _getCalls;

        public FaultInjectingRepository(IStrmFingerprintRepository? inner = null)
        {
            _inner = inner ?? new InMemoryStrmFingerprintRepository();
        }

        public int FailGetAfter { get; init; }

        public bool FailCommit { get; init; }

        public StrmFingerprint? Get(Guid itemId, string sourceKey)
        {
            if (Interlocked.Increment(ref _getCalls) > FailGetAfter)
            {
                throw new IOException("Injected fingerprint store read failure.");
            }

            return _inner.Get(itemId, sourceKey);
        }

        public bool TryCommit(StrmFingerprint candidate, StrmFingerprint? expectedPrevious)
        {
            if (FailCommit)
            {
                throw new IOException("Injected fingerprint commit failure.");
            }

            return _inner.TryCommit(candidate, expectedPrevious);
        }
    }
}
