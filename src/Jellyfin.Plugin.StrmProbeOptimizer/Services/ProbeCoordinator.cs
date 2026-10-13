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
    internal ProbeReservation(ProbeWorkItem item, SemaphoreSlim? permit, bool owner)
    {
        Item = item;
        Permit = permit;
        IsOwner = owner;
    }

    internal ProbeWorkItem Item { get; }

    /// <summary>Gets the global permit owned by this call, or <c>null</c> for a follower.</summary>
    public SemaphoreSlim? Permit { get; }

    /// <summary>Gets a value indicating whether this call owns the reservation and may start the probe.</summary>
    public bool IsOwner { get; }

    /// <summary>Gets the running probe to join when this call is not the owner, otherwise <c>null</c>.</summary>
    public Task<MediaSourceInfo?>? Result => IsOwner ? null : Item.Result;
}

/// <summary>
/// Owns the shared result and global permit for one probe that has actually started.
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
    /// Gets or sets the content hash of the manifest that this running probe is verifying. It is set
    /// immediately before the probe is registered and is used to decide whether a shared failure still applies.
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
/// Queued or waiting work is never registered as shareable, and a finished item is removed before its
/// permit is released so it can never be reused as an in-flight probe.
/// </summary>
public sealed class ProbeCoordinator : IDisposable
{
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

    /// <summary>Gets the number of probes currently registered as running.</summary>
    public int RunningCount => _running.Count;

    /// <summary>Gets the number of global permits currently held.</summary>
    public int ActivePermits => MaxConcurrentProbes - _permits.CurrentCount;

    /// <summary>
    /// Waits for a global permit. The caller becomes the owner unless an identical probe is already running,
    /// in which case it becomes a follower that can join that running probe without taking a second permit.
    /// </summary>
    public async Task<ProbeReservation> AcquireAsync(
        Guid projectItemId,
        string sourceKey,
        string manifestContentHash,
        CancellationToken cancellationToken)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(sourceKey);
        ObjectDisposedException.ThrowIf(Volatile.Read(ref _disposed) != 0, this);
        await _permits.WaitAsync(cancellationToken).ConfigureAwait(false);

        try
        {
            var key = (projectItemId, sourceKey);
            if (_running.TryGetValue(key, out var running))
            {
                // An identical probe is already executing. Do not take a second permit for the same work.
                _permits.Release();
                return new ProbeReservation(running, permit: null, owner: false);
            }

            return new ProbeReservation(new ProbeWorkItem(projectItemId, sourceKey, manifestContentHash), _permits, owner: true);
        }
        catch
        {
            _permits.Release();
            throw;
        }
    }

    /// <summary>
    /// Tries to find an already running probe for the same project and source without waiting for a permit.
    /// </summary>
    public bool TryGetRunning(Guid projectItemId, string sourceKey, out ProbeWorkItem? running)
    {
        return _running.TryGetValue((projectItemId, sourceKey), out running);
    }

    /// <summary>
    /// Registers the reserved work item as running. Call this from the access layer immediately before
    /// entering the matching native probe call. On failure another identical probe won the start race.
    /// </summary>
    public bool TryMarkStarted(ProbeWorkItem item, out ProbeWorkItem? existing)
    {
        ArgumentNullException.ThrowIfNull(item);
        ObjectDisposedException.ThrowIf(Volatile.Read(ref _disposed) != 0, this);
        if (_running.TryAdd((item.ProjectItemId, item.SourceKey), item))
        {
            item.Permit = _permits;
            existing = null;
            return true;
        }

        existing = _running[(item.ProjectItemId, item.SourceKey)];
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

    public void Dispose()
    {
        if (Interlocked.Exchange(ref _disposed, 1) != 0)
        {
            return;
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
        // Remove before releasing the permit so a queued waiter that acquires it cannot reuse a finished item.
        _running.TryRemove((item.ProjectItemId, item.SourceKey), out _);
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
