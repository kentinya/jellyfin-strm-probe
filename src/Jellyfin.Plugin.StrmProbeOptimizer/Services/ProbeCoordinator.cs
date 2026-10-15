using MediaBrowser.Model.Dto;

namespace Jellyfin.Plugin.StrmProbeOptimizer.Services;

/// <summary>
/// The result of reserving a global probe slot. A follower must re-read the current manifest and
/// fingerprint before reusing a shared result. An owner holds <see cref="Permit"/> until it either
/// starts the probe or abandons the reservation.
/// </summary>
public sealed record ProbeReservation
{
    internal ProbeReservation(ProbeWorkItem item, SemaphoreSlim? permit, bool owner, bool running, bool waited)
    {
        Item = item;
        Permit = permit;
        IsOwner = owner;
        IsRunning = running;
        Waited = waited;
    }

    internal ProbeWorkItem Item { get; }

    /// <summary>Gets the global permit owned by this call, or <c>null</c> for a follower.</summary>
    public SemaphoreSlim? Permit { get; }

    /// <summary>Gets a value indicating whether this call owns the reservation and may start the probe.</summary>
    public bool IsOwner { get; }

    /// <summary>
    /// Gets a value indicating whether this call joined a probe whose matching native call has already
    /// started. When <c>false</c> the reserved work is still preparing and must not be reported as started.
    /// </summary>
    public bool IsRunning { get; }

    /// <summary>
    /// Gets a value indicating whether this owner had to wait for a global permit or a preparing owner before
    /// obtaining its execution opportunity. A waiting owner must re-read the current version and configuration.
    /// </summary>
    public bool Waited { get; }

    /// <summary>Gets the running probe to join when this call is not the owner, otherwise <c>null</c>.</summary>
    public Task<MediaSourceInfo?>? Result => IsOwner ? null : Item.Result;
}

/// <summary>
/// Thrown when the access layer observes the matching native probe call for a reservation that is no longer
/// the current owner. The native call must be aborted instead of starting a duplicate probe.
/// </summary>
public sealed class ProbeStartRejectedException : InvalidOperationException
{
    public ProbeStartRejectedException(Guid projectItemId, string sourceKey)
        : base($"A same-source native probe is already registered for item {projectItemId}, source {sourceKey}.")
    {
    }
}

/// <summary>
/// Owns the shared result and global permit for one probe. An item is first registered as preparing and
/// only becomes shareable after the access layer observes the matching native probe call.
/// </summary>
public sealed class ProbeWorkItem
{
    private readonly TaskCompletionSource<MediaSourceInfo?> _completion = new(TaskCreationOptions.RunContinuationsAsynchronously);

    internal ProbeWorkItem(Guid projectItemId, string sourceKey, string manifestContentHash)
    {
        ProjectItemId = projectItemId;
        SourceKey = sourceKey;
        ManifestContentHash = manifestContentHash;
    }

    public Guid ProjectItemId { get; }

    public string SourceKey { get; }

    /// <summary>
    /// Gets or sets the content hash of the manifest that this running probe is verifying. It is refreshed
    /// when a queued owner re-reads the current version before starting and is used to decide whether a
    /// shared failure still applies.
    /// </summary>
    internal string ManifestContentHash { get; set; }

    /// <summary>
    /// Gets a value indicating whether the owner of this work item conditionally committed the verified
    /// result for <see cref="ManifestContentHash"/>. It is set exactly once at settlement and lets a same-source
    /// waiter associate this run's execution with a reliable, committed result instead of reusing a wait return.
    /// It stays <c>null</c> for a reservation that was abandoned or failed without a commit.
    /// </summary>
    public bool? Committed { get; internal set; }

    /// <summary>
    /// Gets or sets the global permit held by this reservation. It is cleared exactly once by
    /// <see cref="ProbeCoordinator.Finish"/> so repeated settlement cannot release twice.
    /// </summary>
    internal SemaphoreSlim? Permit;

    /// <summary>
    /// Gets a value indicating whether the owner observed a fingerprint store fault after the native probe
    /// actually started. It is set exactly once at settlement so a same-source batch waiter can report the
    /// execution-stage store unavailability instead of silently classifying the joined work as a generic
    /// incomplete probe. It stays <c>false</c> for a reservation that never reached a store fault.
    /// </summary>
    public bool FingerprintStoreUnavailable { get; internal set; }

    internal Task<MediaSourceInfo?> Result => _completion.Task;

    internal void Complete(MediaSourceInfo? result)
    {
        _completion.TrySetResult(result);
    }

    internal void Fail(Exception exception)
    {
        _completion.TrySetException(exception);
    }
}

/// <summary>
/// Shares only probes that have actually entered a matching native probe call and are still running.
/// A reservation that is still preparing is not shareable, and a finished item is removed before its
/// permit is released so it can never be reused as an in-flight probe.
/// </summary>
/// <remarks>
/// All registration transitions (running lookup, preparing lookup, preparing insert, preparing-to-running
/// transition and removal) happen under one short-lived gate. That makes the start boundary atomic: a caller
/// can never observe "no running" and then insert a second owner while the first owner is transitioning to
/// running. Native calls, file/database work and task notifications all happen outside the gate.
/// </remarks>
public sealed class ProbeCoordinator : IDisposable
{
    private readonly object _gate = new();
    private readonly Dictionary<(Guid ProjectItemId, string SourceKey), ProbeWorkItem> _preparing = new();
    private readonly Dictionary<(Guid ProjectItemId, string SourceKey), ProbeWorkItem> _running = new();
    private readonly SemaphoreSlim _permits;
    private int _disposed;

    public ProbeCoordinator(int maxConcurrentProbes)
    {
        if (maxConcurrentProbes < PluginConfiguration.MinMaxConcurrentProbes
            || maxConcurrentProbes > PluginConfiguration.MaxMaxConcurrentProbes)
        {
            throw new ArgumentOutOfRangeException(nameof(maxConcurrentProbes));
        }

        MaxConcurrentProbes = maxConcurrentProbes;
        _permits = new SemaphoreSlim(maxConcurrentProbes, maxConcurrentProbes);
    }

    public int MaxConcurrentProbes { get; }

    /// <summary>
    /// Gets or sets a test-only barrier that runs after a global permit has been acquired and before the
    /// registration gate. It lets a deterministic regression force a caller to hold a permit without having
    /// registered yet, so a concurrent start can be interleaved. It is <c>null</c> in production.
    /// </summary>
    internal Action? PermitAcquiredBarrier { get; set; }

    /// <summary>Gets the number of probes whose matching native call has actually started.</summary>
    public int RunningCount
    {
        get
        {
            lock (_gate)
            {
                return _running.Count;
            }
        }
    }

    /// <summary>Gets the number of owners that hold a permit and are still preparing a native probe.</summary>
    public int PreparingCount
    {
        get
        {
            lock (_gate)
            {
                return _preparing.Count;
            }
        }
    }

    /// <summary>Gets the number of global permits currently held.</summary>
    public int ActivePermits => MaxConcurrentProbes - _permits.CurrentCount;

    /// <summary>
    /// Waits for a global permit. The caller becomes the owner unless an identical probe is already
    /// running or preparing, in which case it becomes a follower that can join that work without taking
    /// a second permit. Only the owner may start the native probe.
    /// </summary>
    public async Task<ProbeReservation> AcquireAsync(
        Guid projectItemId,
        string sourceKey,
        string manifestContentHash,
        CancellationToken cancellationToken)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(sourceKey);
        ObjectDisposedException.ThrowIf(Volatile.Read(ref _disposed) != 0, this);
        var acquiredImmediately = _permits.Wait(0);
        if (!acquiredImmediately)
        {
            await _permits.WaitAsync(cancellationToken).ConfigureAwait(false);
        }

        PermitAcquiredBarrier?.Invoke();

        var key = (projectItemId, sourceKey);
        lock (_gate)
        {
            if (_running.TryGetValue(key, out var running))
            {
                // An identical probe has actually started. Do not take a second permit for the same work.
                _permits.Release();
                return new ProbeReservation(running, permit: null, owner: false, running: true, waited: !acquiredImmediately);
            }

            if (_preparing.TryGetValue(key, out var preparing))
            {
                // An identical owner is preparing its native probe but has not reached the matching call yet.
                // Wait for it instead of starting a duplicate; this is not a shared running probe.
                _permits.Release();
                return new ProbeReservation(preparing, permit: null, owner: false, running: false, waited: true);
            }

            var item = new ProbeWorkItem(projectItemId, sourceKey, manifestContentHash) { Permit = _permits };
            _preparing.Add(key, item);
            return new ProbeReservation(item, _permits, owner: true, running: false, waited: !acquiredImmediately);
        }
    }

    /// <summary>
    /// Tries to find an already running probe for the same project and source without waiting for a permit.
    /// </summary>
    public bool TryGetRunning(Guid projectItemId, string sourceKey, out ProbeWorkItem? running)
    {
        lock (_gate)
        {
            return _running.TryGetValue((projectItemId, sourceKey), out running);
        }
    }

    /// <summary>
    /// Registers the reserved work item as running. Call this from the access layer at the verified
    /// matching native probe call. A preparing reservation is not shareable and must not call this.
    /// </summary>
    public bool TryMarkStarted(ProbeWorkItem item, out ProbeWorkItem? existing)
    {
        ArgumentNullException.ThrowIfNull(item);
        ObjectDisposedException.ThrowIf(Volatile.Read(ref _disposed) != 0, this);
        var key = (item.ProjectItemId, item.SourceKey);
        lock (_gate)
        {
            if (_running.TryGetValue(key, out var running))
            {
                // Another owner already published this key. This reservation must not start a duplicate.
                RemoveIfCurrent(_preparing, key, item);
                existing = running;
                return false;
            }

            if (!_preparing.TryGetValue(key, out var current) || !ReferenceEquals(current, item))
            {
                existing = null;
                return false;
            }

            _running.Add(key, item);
            _preparing.Remove(key);
            existing = null;
            return true;
        }
    }

    /// <summary>
    /// Releases the running registration and the global permit, then publishes the shared result.
    /// Safe on every completion path, including failure and cancellation.
    /// </summary>
    /// <param name="item">The settled work item.</param>
    /// <param name="result">The accepted media source, or <c>null</c>.</param>
    public void Complete(ProbeWorkItem item, MediaSourceInfo? result)
    {
        ArgumentNullException.ThrowIfNull(item);
        Finish(item, result, exception: null, committed: false, fingerprintStoreUnavailable: false);
    }

    /// <summary>
    /// Releases the running registration and the global permit, then publishes the shared result together with
    /// the owner's conditional-commit outcome. A waiter can use <see cref="ProbeWorkItem.Committed"/> to associate
    /// this run's execution with a reliable success instead of counting a wait return as success.
    /// </summary>
    /// <param name="item">The settled work item.</param>
    /// <param name="result">The accepted media source, or <c>null</c>.</param>
    /// <param name="committed"><c>true</c> only when the owner conditionally committed the verified result.</param>
    public void Complete(ProbeWorkItem item, MediaSourceInfo? result, bool committed)
    {
        ArgumentNullException.ThrowIfNull(item);
        Finish(item, result, exception: null, committed, fingerprintStoreUnavailable: false);
    }

    /// <summary>
    /// Releases the running registration and the global permit, then publishes the shared result together with
    /// the owner's conditional-commit outcome and the execution-stage fingerprint store state. A same-source batch
    /// waiter uses both to report this run's execution as a reliable success or as an execution-stage store fault,
    /// never as a generic incomplete probe or a revoked candidate.
    /// </summary>
    /// <param name="item">The settled work item.</param>
    /// <param name="result">The accepted media source, or <c>null</c>.</param>
    /// <param name="committed"><c>true</c> only when the owner conditionally committed the verified result.</param>
    /// <param name="fingerprintStoreUnavailable"><c>true</c> when the verified result could not be committed because the store faulted.</param>
    public void Complete(ProbeWorkItem item, MediaSourceInfo? result, bool committed, bool fingerprintStoreUnavailable)
    {
        ArgumentNullException.ThrowIfNull(item);
        Finish(item, result, exception: null, committed, fingerprintStoreUnavailable);
    }

    /// <summary>
    /// Releases the running registration and the global permit, then publishes the failure to every waiter.
    /// </summary>
    public void Fail(ProbeWorkItem item, Exception exception)
    {
        ArgumentNullException.ThrowIfNull(item);
        ArgumentNullException.ThrowIfNull(exception);
        Finish(item, result: null, exception, committed: false, fingerprintStoreUnavailable: false);
    }

    /// <summary>
    /// Releases a reservation that will not start a native probe, for example because a queued owner
    /// re-read the current version or configuration and no longer needs to probe. Waiters re-evaluate.
    /// </summary>
    public void Abandon(ProbeWorkItem item)
    {
        ArgumentNullException.ThrowIfNull(item);
        Finish(item, result: null, exception: null, committed: false, fingerprintStoreUnavailable: false);
    }

    public void Dispose()
    {
        if (Interlocked.Exchange(ref _disposed, 1) != 0)
        {
            return;
        }

        var pending = new List<ProbeWorkItem>();
        lock (_gate)
        {
            foreach (var item in _preparing.Values)
            {
                pending.Add(item);
                Interlocked.Exchange(ref item.Permit, null);
            }

            foreach (var item in _running.Values)
            {
                pending.Add(item);
                Interlocked.Exchange(ref item.Permit, null);
            }

            _preparing.Clear();
            _running.Clear();
        }

        foreach (var item in pending)
        {
            item.Fail(new ObjectDisposedException(nameof(ProbeCoordinator)));
        }

        _permits.Dispose();
    }

    private static void RemoveIfCurrent(
        Dictionary<(Guid ProjectItemId, string SourceKey), ProbeWorkItem> map,
        (Guid ProjectItemId, string SourceKey) key,
        ProbeWorkItem item)
    {
        if (map.TryGetValue(key, out var current) && ReferenceEquals(current, item))
        {
            map.Remove(key);
        }
    }

    private void Finish(ProbeWorkItem item, MediaSourceInfo? result, Exception? exception, bool committed, bool fingerprintStoreUnavailable)
    {
        var key = (item.ProjectItemId, item.SourceKey);
        SemaphoreSlim? permit;
        lock (_gate)
        {
            // Clearing the permit exactly once makes settlement idempotent: a repeated Complete/Fail/Abandon
            // cannot release the semaphore twice or remove a newer registration for the same key.
            permit = Interlocked.Exchange(ref item.Permit, null);
            if (permit is null)
            {
                return;
            }

            RemoveIfCurrent(_preparing, key, item);
            RemoveIfCurrent(_running, key, item);
        }

        // Publish the commit outcome before resolving the shared result so a waiter that observes the completed
        // result also observes the owner's this-run conditional-commit association.
        item.Committed = exception is null && committed;
        item.FingerprintStoreUnavailable = exception is null && fingerprintStoreUnavailable;
        try
        {
            if (exception is null)
            {
                item.Complete(result);
            }
            else
            {
                item.Fail(exception);
            }
        }
        finally
        {
            permit.Release();
        }
    }
}
