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
    public async Task QueuedReservationIsNotShareableUntilItActuallyStarts()
    {
        using var coordinator = new ProbeCoordinator(2);

        var first = await coordinator.AcquireAsync(ProjectA, SourceA, HashOne, CancellationToken.None);
        Assert.IsTrue(first.IsOwner, "The first reservation must own the start.");
        Assert.IsFalse(coordinator.TryGetRunning(ProjectA, SourceA, out _), "A reservation that has not started must not be registered as running.");
        Assert.AreEqual(0, coordinator.RunningCount);
        Assert.AreEqual(1, coordinator.ActivePermits, "A queued reservation still holds its global permit.");

        // A second caller for the same source must not join an unstarted reservation.
        var second = await coordinator.AcquireAsync(ProjectA, SourceA, HashOne, CancellationToken.None);
        Assert.IsTrue(second.IsOwner, "An unstarted reservation must not be shared; the second caller becomes its own owner.");
        Assert.AreEqual(2, coordinator.ActivePermits);

        first.Permit!.Release();
        second.Permit!.Release();
    }

    [TestMethod]
    public async Task ActuallyStartedProbeIsSharedWithSameSourceCallers()
    {
        using var coordinator = new ProbeCoordinator(2);
        var owner = await coordinator.AcquireAsync(ProjectA, SourceA, HashOne, CancellationToken.None);
        Assert.IsTrue(coordinator.TryMarkStarted(owner.Item, out _), "The owner must be able to register the running probe.");
        Assert.AreEqual(1, coordinator.RunningCount);
        Assert.AreEqual(1, coordinator.ActivePermits, "Starting must not take a second permit.");

        var follower = await coordinator.AcquireAsync(ProjectA, SourceA, HashTwo, CancellationToken.None);
        Assert.IsFalse(follower.IsOwner, "An actually running probe must be shared.");
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
    public async Task PermitIsReleasedOnSuccessAndFailure()
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
        Assert.IsTrue(racing.IsOwner);

        Assert.IsTrue(coordinator.TryMarkStarted(owner.Item, out var none));
        Assert.IsNull(none);
        Assert.IsFalse(coordinator.TryMarkStarted(racing.Item, out var existing), "A second identical start must be rejected.");
        Assert.AreSame(owner.Item, existing);
        Assert.AreEqual(1, coordinator.RunningCount);

        coordinator.Complete(owner.Item, null);
        racing.Permit!.Release();
        Assert.AreEqual(0, coordinator.ActivePermits);
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
