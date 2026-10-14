using Jellyfin.Plugin.StrmProbeOptimizer.Services;
using MediaBrowser.Model.Dto;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace Jellyfin.Plugin.StrmProbeOptimizer.Tests;

[TestClass]
public sealed class ProbeCoordinatorTests
{
    private static readonly Guid ProjectA = Guid.Parse("11111111-1111-1111-1111-111111111111");
    private static readonly Guid ProjectB = Guid.Parse("22222222-2222-2222-2222-222222222222");
    private const string SourceA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    private const string SourceB = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
    private const string HashOne = "hash-one";
    private const string HashTwo = "hash-two";

    [TestMethod]
    public async Task PreparingReservationIsNotRunningAndNotSharedAsStarted()
    {
        using var coordinator = new ProbeCoordinator(2);

        var first = await coordinator.AcquireAsync(ProjectA, SourceA, HashOne, CancellationToken.None);
        Assert.IsTrue(first.IsOwner, "The first reservation must own the start.");
        Assert.IsFalse(first.IsRunning, "A reservation that has not reached the matching native call is not running.");
        Assert.IsFalse(coordinator.TryGetRunning(ProjectA, SourceA, out _), "A preparing reservation must not be registered as running.");
        Assert.AreEqual(0, coordinator.RunningCount);
        Assert.AreEqual(1, coordinator.PreparingCount, "A preparing owner is tracked separately from running probes.");
        Assert.AreEqual(1, coordinator.ActivePermits, "A preparing reservation still holds its global permit.");

        // A second caller for the same source must not be reported as joining a running probe. It waits for the
        // preparing owner instead of starting a duplicate.
        var second = await coordinator.AcquireAsync(ProjectA, SourceA, HashOne, CancellationToken.None);
        Assert.IsFalse(second.IsOwner, "A preparing reservation must not be shared as an owner; the second caller waits.");
        Assert.IsFalse(second.IsRunning, "The preparing work must not be reported as running.");
        Assert.IsNull(second.Permit, "Waiting for a preparing owner must not take a second permit.");
        Assert.AreEqual(1, coordinator.ActivePermits);
        Assert.AreEqual(1, coordinator.PreparingCount);

        coordinator.Abandon(first.Item);
        Assert.AreEqual(0, coordinator.PreparingCount);
        Assert.AreEqual(0, coordinator.ActivePermits);
        await second.Result!;
    }

    [TestMethod]
    public async Task ActuallyStartedProbeIsSharedWithSameSourceCallers()
    {
        using var coordinator = new ProbeCoordinator(2);
        var owner = await coordinator.AcquireAsync(ProjectA, SourceA, HashOne, CancellationToken.None);
        Assert.IsTrue(coordinator.TryMarkStarted(owner.Item, out _), "The owner must be able to register the running probe.");
        Assert.AreEqual(1, coordinator.RunningCount);
        Assert.AreEqual(0, coordinator.PreparingCount);
        Assert.AreEqual(1, coordinator.ActivePermits, "Starting must not take a second permit.");

        var follower = await coordinator.AcquireAsync(ProjectA, SourceA, HashTwo, CancellationToken.None);
        Assert.IsFalse(follower.IsOwner, "An actually running probe must be shared.");
        Assert.IsTrue(follower.IsRunning, "The follower must be reported as joining a running probe.");
        Assert.IsNull(follower.Permit, "Joining a running probe must not consume an additional global permit.");
        Assert.AreEqual(1, coordinator.ActivePermits);

        var result = new MediaSourceInfo { Path = "https://media.example.invalid/video.mp4" };
        coordinator.Complete(owner.Item, result);
        Assert.AreSame(result, await follower.Result!, "The follower must observe the shared result.");

        var afterCompletion = await coordinator.AcquireAsync(ProjectA, SourceA, HashOne, CancellationToken.None);
        Assert.IsTrue(afterCompletion.IsOwner, "A completed probe must never be reused as an in-flight probe.");
        afterCompletion.Permit!.Release();
    }

    [TestMethod]
    public async Task DifferentSourcesAndProjectsDoNotShare()
    {
        using var coordinator = new ProbeCoordinator(3);
        var first = await coordinator.AcquireAsync(ProjectA, SourceA, HashOne, CancellationToken.None);
        Assert.IsTrue(coordinator.TryMarkStarted(first.Item, out _));

        var otherSource = await coordinator.AcquireAsync(ProjectA, SourceB, HashOne, CancellationToken.None);
        Assert.IsTrue(otherSource.IsOwner, "A different media source must not share the running probe.");

        var otherProject = await coordinator.AcquireAsync(ProjectB, SourceA, HashOne, CancellationToken.None);
        Assert.IsTrue(otherProject.IsOwner, "A different project must not share the running probe.");

        first.Permit!.Release();
        otherSource.Permit!.Release();
        otherProject.Permit!.Release();
    }

    [TestMethod]
    public async Task GlobalLimitCapsConcurrentStartedProbes()
    {
        using var coordinator = new ProbeCoordinator(2);
        var first = await coordinator.AcquireAsync(ProjectA, SourceA, HashOne, CancellationToken.None);
        var second = await coordinator.AcquireAsync(ProjectB, SourceB, HashOne, CancellationToken.None);
        Assert.IsTrue(coordinator.TryMarkStarted(first.Item, out _));
        Assert.IsTrue(coordinator.TryMarkStarted(second.Item, out _));
        Assert.AreEqual(2, coordinator.RunningCount);

        var third = coordinator.AcquireAsync(ProjectA, SourceB, HashOne, CancellationToken.None);
        Assert.IsFalse(third.IsCompleted, "The third probe must wait for a free global permit.");

        coordinator.Complete(first.Item, null);
        var thirdReservation = await third;
        Assert.IsTrue(thirdReservation.IsOwner, "The waiting caller must obtain the freed permit.");
        Assert.AreEqual(2, coordinator.ActivePermits);

        second.Permit!.Release();
        thirdReservation.Permit!.Release();
    }

    [TestMethod]
    public async Task GlobalLimitOneSerializesAndGlobalLimitEightAllowsEight()
    {
        // Configured limit 1: the second start cannot hold a permit until the first finishes.
        using var single = new ProbeCoordinator(1);
        var owner = await single.AcquireAsync(ProjectA, SourceA, HashOne, CancellationToken.None);
        Assert.IsTrue(single.TryMarkStarted(owner.Item, out _), "The limit-1 boundary must be measured with an actually started probe.");
        Assert.AreEqual(1, single.RunningCount);
        var blocked = single.AcquireAsync(ProjectB, SourceB, HashOne, CancellationToken.None);
        Assert.IsFalse(blocked.IsCompleted, "A configured limit of 1 must serialize a second source.");
        single.Complete(owner.Item, null);
        var admitted = await blocked;
        Assert.IsTrue(admitted.IsOwner);
        single.Abandon(admitted.Item);
        Assert.AreEqual(0, single.ActivePermits);

        // Configured limit 8: eight distinct sources may hold permits and start concurrently; the ninth waits.
        using var eight = new ProbeCoordinator(8);
        var holders = new List<ProbeReservation>();
        for (var index = 0; index < 8; index++)
        {
            var reservation = await eight.AcquireAsync(Guid.NewGuid(), SourceA, HashOne, CancellationToken.None);
            Assert.IsTrue(reservation.IsOwner);
            Assert.IsTrue(eight.TryMarkStarted(reservation.Item, out _));
            holders.Add(reservation);
        }

        Assert.AreEqual(8, eight.RunningCount);
        Assert.AreEqual(8, eight.ActivePermits);
        var ninth = eight.AcquireAsync(Guid.NewGuid(), SourceA, HashOne, CancellationToken.None);
        Assert.IsFalse(ninth.IsCompleted, "The ninth source must wait at the configured limit of 8.");
        eight.Complete(holders[0].Item, null);
        var ninthReservation = await ninth;
        Assert.IsTrue(ninthReservation.IsOwner);
        foreach (var holder in holders.Skip(1))
        {
            eight.Complete(holder.Item, null);
        }

        eight.Abandon(ninthReservation.Item);
        Assert.AreEqual(0, eight.ActivePermits);
    }

    [TestMethod]
    public async Task PermitIsReleasedOnSuccessFailureAndAbandon()
    {
        using var coordinator = new ProbeCoordinator(2);
        var success = await coordinator.AcquireAsync(ProjectA, SourceA, HashOne, CancellationToken.None);
        Assert.IsTrue(coordinator.TryMarkStarted(success.Item, out _));
        coordinator.Complete(success.Item, null);
        Assert.AreEqual(0, coordinator.ActivePermits);
        Assert.AreEqual(0, coordinator.RunningCount);

        var failure = await coordinator.AcquireAsync(ProjectB, SourceB, HashOne, CancellationToken.None);
        Assert.IsTrue(coordinator.TryMarkStarted(failure.Item, out _));
        coordinator.Fail(failure.Item, new InvalidOperationException("injected failure"));
        Assert.AreEqual(0, coordinator.ActivePermits);
        Assert.AreEqual(0, coordinator.RunningCount);

        var abandoned = await coordinator.AcquireAsync(ProjectA, SourceB, HashOne, CancellationToken.None);
        coordinator.Abandon(abandoned.Item);
        Assert.AreEqual(0, coordinator.ActivePermits);
        Assert.AreEqual(0, coordinator.PreparingCount);
    }

    [TestMethod]
    public async Task WaitingCallerCancellationDoesNotCancelTheRunningProbe()
    {
        using var coordinator = new ProbeCoordinator(1);
        var owner = await coordinator.AcquireAsync(ProjectA, SourceA, HashOne, CancellationToken.None);
        Assert.IsTrue(coordinator.TryMarkStarted(owner.Item, out _));

        using var cancellation = new CancellationTokenSource();
        var waiter = coordinator.AcquireAsync(ProjectB, SourceB, HashOne, cancellation.Token);
        cancellation.Cancel();
        await Assert.ThrowsExactlyAsync<OperationCanceledException>(() => waiter);

        // The running probe still completes and releases its permit even though the waiter gave up.
        var result = new MediaSourceInfo { Path = "https://media.example.invalid/video.mp4" };
        coordinator.Complete(owner.Item, result);
        Assert.AreEqual(0, coordinator.ActivePermits);
        Assert.AreEqual(0, coordinator.RunningCount);
    }

    [TestMethod]
    public async Task StartRaceRegistersExactlyOneRunningProbe()
    {
        using var coordinator = new ProbeCoordinator(2);
        var owner = await coordinator.AcquireAsync(ProjectA, SourceA, HashOne, CancellationToken.None);
        var racing = await coordinator.AcquireAsync(ProjectA, SourceA, HashOne, CancellationToken.None);
        Assert.IsFalse(racing.IsOwner, "A concurrent same-key reservation waits for the preparing owner.");

        Assert.IsTrue(coordinator.TryMarkStarted(owner.Item, out var none));
        Assert.IsNull(none);
        Assert.AreEqual(1, coordinator.RunningCount);
        Assert.AreEqual(0, coordinator.PreparingCount);
        Assert.IsTrue(racing.IsRunning == false, "The queued follower was told the owner was preparing, not running.");
        Assert.AreSame(owner.Item, racing.Item);

        coordinator.Complete(owner.Item, null);
        Assert.AreEqual(0, coordinator.ActivePermits);
        Assert.AreEqual(0, coordinator.RunningCount);
        Assert.AreEqual(0, coordinator.PreparingCount);
    }

    [TestMethod]
    public async Task AbandoningPreparingWorkWakesWaitersForReevaluation()
    {
        using var coordinator = new ProbeCoordinator(2);
        var owner = await coordinator.AcquireAsync(ProjectA, SourceA, HashOne, CancellationToken.None);
        var waiter = await coordinator.AcquireAsync(ProjectA, SourceA, HashTwo, CancellationToken.None);
        Assert.IsFalse(waiter.IsOwner);

        coordinator.Abandon(owner.Item);

        // The waiter's shared task completes so the access layer re-evaluates the current version instead of
        // reusing a result, and the permit is released.
        await waiter.Result!;
        Assert.AreEqual(0, coordinator.ActivePermits);
        Assert.AreEqual(0, coordinator.PreparingCount);
        Assert.AreEqual(0, coordinator.RunningCount);
    }

    [TestMethod]
    public async Task StartRaceWithSecondCallerHoldingAPermitCannotCreateASecondOwner()
    {
        using var coordinator = new ProbeCoordinator(2);
        var first = await coordinator.AcquireAsync(ProjectA, SourceA, HashOne, CancellationToken.None);
        Assert.IsTrue(first.IsOwner);

        // Force the second caller to hold a global permit but pause before it enters the registration gate.
        var barrierReached = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var releaseBarrier = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        coordinator.PermitAcquiredBarrier = () =>
        {
            barrierReached.TrySetResult();
            releaseBarrier.Task.Wait(TimeSpan.FromSeconds(10));
        };

        var secondTask = Task.Run(() => coordinator.AcquireAsync(ProjectA, SourceA, HashOne, CancellationToken.None));
        await barrierReached.Task.WaitAsync(TimeSpan.FromSeconds(10));

        // The first owner publishes the running probe while the second caller is between permit acquisition
        // and registration. This is exactly the interleaving that used to produce a second owner.
        Assert.IsTrue(coordinator.TryMarkStarted(first.Item, out _));
        Assert.AreEqual(1, coordinator.RunningCount);
        Assert.AreEqual(0, coordinator.PreparingCount);
        Assert.AreEqual(2, coordinator.ActivePermits, "Both callers hold a permit while the second is paused before registration.");

        releaseBarrier.TrySetResult();
        var second = await secondTask.WaitAsync(TimeSpan.FromSeconds(10));

        // The atomic registration gate must make the second caller observe the running probe and become a
        // follower, releasing its spare permit. A second owner here would duplicate the native probe.
        Assert.IsFalse(second.IsOwner, "The atomic gate must not allow a second owner for the same key.");
        Assert.IsTrue(second.IsRunning);
        Assert.IsNull(second.Permit);
        Assert.AreEqual(1, coordinator.ActivePermits, "The follower must release its redundant permit.");
        Assert.AreEqual(1, coordinator.RunningCount);

        coordinator.Complete(first.Item, null);
        await second.Result!;
        Assert.AreEqual(0, coordinator.ActivePermits);
        Assert.AreEqual(0, coordinator.RunningCount);
    }

    [TestMethod]
    public void TryMarkStartedAfterSettlementIsRejectedWithoutPublishingARunningProbe()
    {
        using var coordinator = new ProbeCoordinator(2);
        var owner = coordinator.AcquireAsync(ProjectA, SourceA, HashOne, CancellationToken.None).GetAwaiter().GetResult();
        coordinator.Abandon(owner.Item);

        // A reservation that has already been settled is no longer the current owner and must not publish a
        // running entry; the access layer relies on this to abort a redundant native call.
        Assert.IsFalse(coordinator.TryMarkStarted(owner.Item, out var existing));
        Assert.IsNull(existing);
        Assert.AreEqual(0, coordinator.RunningCount);
        Assert.AreEqual(0, coordinator.PreparingCount);
        Assert.AreEqual(0, coordinator.ActivePermits);
    }

    [TestMethod]
    public async Task StaleSettlementDoesNotRemoveANewerRegistrationOrReleaseTwice()
    {
        using var coordinator = new ProbeCoordinator(2);
        var stale = await coordinator.AcquireAsync(ProjectA, SourceA, HashOne, CancellationToken.None);
        coordinator.Abandon(stale.Item);

        var fresh = await coordinator.AcquireAsync(ProjectA, SourceA, HashTwo, CancellationToken.None);
        Assert.IsTrue(coordinator.TryMarkStarted(fresh.Item, out _));
        Assert.AreEqual(1, coordinator.RunningCount);
        Assert.AreEqual(1, coordinator.ActivePermits);

        // Re-settling the stale item must be a no-op and must not remove the newer registration for the same key.
        coordinator.Complete(stale.Item, null);
        coordinator.Fail(stale.Item, new InvalidOperationException("stale settlement"));
        coordinator.Abandon(stale.Item);
        Assert.AreEqual(1, coordinator.RunningCount, "A stale settlement must not remove a newer registration.");
        Assert.AreEqual(1, coordinator.ActivePermits, "A repeated settlement must not release the permit twice.");

        coordinator.Complete(fresh.Item, null);
        Assert.AreEqual(0, coordinator.RunningCount);
        Assert.AreEqual(0, coordinator.ActivePermits);
    }

    [TestMethod]
    public async Task RepeatedSettlementOfTheSameReservationReleasesExactlyOnce()
    {
        using var coordinator = new ProbeCoordinator(2);
        var owner = await coordinator.AcquireAsync(ProjectA, SourceA, HashOne, CancellationToken.None);
        coordinator.Complete(owner.Item, null);
        Assert.AreEqual(0, coordinator.ActivePermits);

        // Every later settlement of the same work item must be ignored.
        coordinator.Fail(owner.Item, new InvalidOperationException("late failure"));
        coordinator.Abandon(owner.Item);
        Assert.AreEqual(0, coordinator.ActivePermits);
        Assert.AreEqual(0, coordinator.PreparingCount);
        Assert.AreEqual(0, coordinator.RunningCount);
    }

    [TestMethod]
    public void ConstructorRejectsConcurrencyOutsideTheDocumentedRange()
    {
        Assert.ThrowsExactly<ArgumentOutOfRangeException>(() => new ProbeCoordinator(0));
        Assert.ThrowsExactly<ArgumentOutOfRangeException>(() => new ProbeCoordinator(9));
        using var allowedMinimum = new ProbeCoordinator(1);
        using var allowedMaximum = new ProbeCoordinator(8);
        Assert.AreEqual(1, allowedMinimum.MaxConcurrentProbes);
        Assert.AreEqual(8, allowedMaximum.MaxConcurrentProbes);
    }
}
