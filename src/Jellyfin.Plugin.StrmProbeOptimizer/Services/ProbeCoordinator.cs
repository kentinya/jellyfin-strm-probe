using System.Collections.Concurrent;
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

    internal SemaphoreSlim? Permit { get; set; }

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
public sealed class ProbeCoordinator : IDisposable
{
    private readonly ConcurrentDictionary<(Guid ProjectItemId, string SourceKey), ProbeWorkItem> _preparing = new();
    private readonly ConcurrentDictionary<(Guid ProjectItemId, string SourceKey), ProbeWorkItem> _running = new();
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

    /// <summary>Gets the number of probes whose matching native call has actually started.</summary>
    public int RunningCount => _running.Count;

    /// <summary>Gets the number of owners that hold a permit and are still preparing a native probe.</summary>
    public int PreparingCount => _preparing.Count;

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

        var key = (projectItemId, sourceKey);
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
        if (!_preparing.TryAdd(key, item))
        {
            _permits.Release();
            return new ProbeReservation(_preparing[key], permit: null, owner: false, running: false, waited: true);
        }

        return new ProbeReservation(item, _permits, owner: true, running: false, waited: !acquiredImmediately);
    }

    /// <summary>
    /// Tries to find an already running probe for the same project and source without waiting for a permit.
    /// </summary>
    public bool TryGetRunning(Guid projectItemId, string sourceKey, out ProbeWorkItem? running)
    {
        return _running.TryGetValue((projectItemId, sourceKey), out running);
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

        // Publish the running entry before clearing preparing so a concurrent AcquireAsync always sees the
        // running probe first and can never start a duplicate preparation for the same key.
        if (_running.TryAdd(key, item))
        {
            _preparing.TryRemove(new KeyValuePair<(Guid, string), ProbeWorkItem>(key, item));
            existing = null;
            return true;
        }

        existing = _running[key];
        _preparing.TryRemove(new KeyValuePair<(Guid, string), ProbeWorkItem>(key, item));
        return false;
    }

    /// <summary>
    /// Releases the running registration and the global permit, then publishes the shared result.
    /// Safe on every completion path, including failure and cancellation.
    /// </summary>
    public void Complete(ProbeWorkItem item, MediaSourceInfo? result)
    {
        ArgumentNullException.ThrowIfNull(item);
        Finish(item, result, exception: null);
    }

    /// <summary>
    /// Releases the running registration and the global permit, then publishes the failure to every waiter.
    /// </summary>
    public void Fail(ProbeWorkItem item, Exception exception)
    {
        ArgumentNullException.ThrowIfNull(item);
        ArgumentNullException.ThrowIfNull(exception);
        Finish(item, result: null, exception);
    }

    /// <summary>
    /// Releases a reservation that will not start a native probe, for example because a queued owner
    /// re-read the current version or configuration and no longer needs to probe. Waiters re-evaluate.
    /// </summary>
    public void Abandon(ProbeWorkItem item)
    {
        ArgumentNullException.ThrowIfNull(item);
        Finish(item, result: null, exception: null);
    }

    public void Dispose()
    {
        if (Interlocked.Exchange(ref _disposed, 1) != 0)
        {
            return;
        }

        foreach (var pair in _preparing)
        {
            if (_preparing.TryRemove(pair.Key, out var item))
            {
                item.Fail(new ObjectDisposedException(nameof(ProbeCoordinator)));
            }
        }

        foreach (var pair in _running)
        {
            if (_running.TryRemove(pair.Key, out var item))
            {
                item.Fail(new ObjectDisposedException(nameof(ProbeCoordinator)));
            }
        }

        _permits.Dispose();
    }

    private void Finish(ProbeWorkItem item, MediaSourceInfo? result, Exception? exception)
    {
        var key = (item.ProjectItemId, item.SourceKey);

        // Remove before releasing the permit so a queued waiter that acquires it cannot reuse a finished item.
        _preparing.TryRemove(new KeyValuePair<(Guid, string), ProbeWorkItem>(key, item));
        _running.TryRemove(new KeyValuePair<(Guid, string), ProbeWorkItem>(key, item));
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
            item.Permit?.Release();
        }
    }
}
