using Jellyfin.Data.Enums;
using Jellyfin.Plugin.StrmProbeOptimizer.Services;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Library;

namespace Jellyfin.Plugin.StrmProbeOptimizer.Services;

/// <summary>
/// Resolves the stable ids of the media libraries that currently exist. It is a narrow seam so configuration
/// save validation can verify a selection without taking a dependency on the full library manager in tests.
/// </summary>
public interface ILibraryIdProvider
{
    /// <summary>Gets the stable ids of the libraries that currently exist.</summary>
    IReadOnlyCollection<Guid> GetAvailableLibraryIds();
}

/// <summary>
/// The real library id provider backed by the native library manager.
/// </summary>
public sealed class LibraryIdProvider : ILibraryIdProvider
{
    private readonly ILibraryManager _libraryManager;

    public LibraryIdProvider(ILibraryManager libraryManager)
    {
        _libraryManager = libraryManager;
    }

    public IReadOnlyCollection<Guid> GetAvailableLibraryIds()
    {
        var available = new HashSet<Guid>();
        foreach (var folder in _libraryManager.GetVirtualFolders())
        {
            if (Guid.TryParse(folder.ItemId, out var id))
            {
                available.Add(id);
            }
        }

        return available;
    }
}

/// <summary>
/// The fixed media library scope captured for one batch run. <see cref="AllLibraries"/> records that the run
/// resolved the documented default scope; the concrete library ids are always captured so later configuration
/// changes only apply to the next run.
/// </summary>
public sealed record BatchLibraryScope(bool AllLibraries, IReadOnlyList<Guid> LibraryIds);

/// <summary>
/// Thrown when the saved batch scope cannot be resolved to real libraries. The batch reports it as unavailable
/// and starts no probe instead of silently widening the scope to all libraries.
/// </summary>
public sealed class BatchScopeUnavailableException : InvalidOperationException
{
    public BatchScopeUnavailableException(string message)
        : base(message)
    {
    }
}

/// <summary>
/// Resolves the saved batch scope against the real Jellyfin media libraries.
/// </summary>
public interface IBatchScopeResolver
{
    BatchLibraryScope Resolve();
}

public sealed class BatchScopeResolver : IBatchScopeResolver
{
    private readonly ILibraryManager _libraryManager;
    private readonly IPlaybackSettings _settings;

    public BatchScopeResolver(ILibraryManager libraryManager, IPlaybackSettings settings)
    {
        _libraryManager = libraryManager;
        _settings = settings;
    }

    public BatchLibraryScope Resolve()
    {
        var folders = _libraryManager.GetVirtualFolders();
        var all = new List<Guid>();
        var available = new HashSet<Guid>();
        foreach (var folder in folders)
        {
            if (Guid.TryParse(folder.ItemId, out var id) && available.Add(id))
            {
                all.Add(id);
            }
        }

        if (_settings.BatchAllLibraries)
        {
            return new BatchLibraryScope(true, all);
        }

        if (!PluginConfiguration.TryParseLibraryIds(_settings.BatchLibraryIds, out var selected) || selected.Count == 0)
        {
            throw new BatchScopeUnavailableException("The saved batch library selection is empty or invalid; re-save the plugin configuration with at least one real library.");
        }

        var missing = selected.Where(id => !available.Contains(id)).ToArray();
        if (missing.Length > 0)
        {
            throw new BatchScopeUnavailableException($"The saved batch library selection references {missing.Length} library id(s) that no longer exist or cannot be identified; re-save the plugin configuration.");
        }

        return new BatchLibraryScope(false, selected);
    }
}

/// <summary>
/// The native query surface the batch uses. It is separated so the deterministic tests can supply a candidate
/// identity set and object batches without a real Jellyfin library.
/// </summary>
public interface IBatchCandidateSource : IBatchScopeVerifier
{
    /// <summary>Gets the raw candidate ids for one library using the native library relationship.</summary>
    IReadOnlyList<Guid> GetLibraryCandidateIds(Guid libraryId);

    /// <summary>Reads the current objects for one fixed id batch, re-checking the scope through the native relationship.</summary>
    IReadOnlyList<BaseItem> GetBatchItems(IReadOnlyList<Guid> ids, IReadOnlyList<Guid> scopeLibraryIds);
}

/// <summary>
/// Re-checks a candidate's current library relationship against the run's fixed scope. It is consulted again at
/// execution admission so an object that left the selected scope, was deleted or changed type while queued is not
/// probed from a stale decision.
/// </summary>
public interface IBatchScopeVerifier
{
    /// <summary>Checks whether the current object still belongs to one of the selected libraries.</summary>
    bool IsInScope(BaseItem item, IReadOnlyList<Guid> scopeLibraryIds);

    /// <summary>
    /// Re-reads the current native object for a candidate. It returns <c>null</c> when the object can no longer
    /// be resolved. The caller uses the returned object as the current identity (project, source key and path)
    /// instead of trusting the object captured before the batch read or before waiting for a permit.
    /// </summary>
    /// <param name="item">The captured candidate object.</param>
    /// <returns>The current native object, or <c>null</c> when it can no longer be resolved.</returns>
    BaseItem? GetCurrentItem(BaseItem item) => item;
}

public sealed class LibraryBatchCandidateSource : IBatchCandidateSource
{
    private readonly ILibraryManager _libraryManager;

    public LibraryBatchCandidateSource(ILibraryManager libraryManager)
    {
        _libraryManager = libraryManager;
    }

    public IReadOnlyList<Guid> GetLibraryCandidateIds(Guid libraryId)
    {
        return _libraryManager.GetItemIds(new InternalItemsQuery
        {
            Recursive = true,
            IsFolder = false,
            IsVirtualItem = false,
            MediaTypes = [MediaType.Video, MediaType.Audio],
            IncludeAlternateVersions = true,
            GroupByPresentationUniqueKey = false,
            CollapseBoxSetItems = false,
            EnableTotalRecordCount = false,
            AncestorIds = [libraryId]
        });
    }

    public IReadOnlyList<BaseItem> GetBatchItems(IReadOnlyList<Guid> ids, IReadOnlyList<Guid> scopeLibraryIds)
    {
        return _libraryManager.GetItemList(new InternalItemsQuery
        {
            ItemIds = [.. ids],
            AncestorIds = [.. scopeLibraryIds],
            IsFolder = false,
            IsVirtualItem = false,
            MediaTypes = [MediaType.Video, MediaType.Audio],
            IncludeAlternateVersions = true,
            GroupByPresentationUniqueKey = false,
            CollapseBoxSetItems = false,
            EnableTotalRecordCount = false
        });
    }

    public bool IsInScope(BaseItem item, IReadOnlyList<Guid> scopeLibraryIds)
    {
        if (scopeLibraryIds.Count == 0)
        {
            return true;
        }

        // Re-read the current object through the native library instead of trusting the stale candidate. A
        // candidate that was deleted, moved out of the selected libraries, changed type or was re-pointed to a
        // different primary version while it was queued must not be probed from a stale object, so admission
        // verifies the current native identity and relationship rather than only the captured parent chain.
        var current = GetCurrentItem(item);
        if (current is null || current.GetType() != item.GetType())
        {
            return false;
        }

        if (GetStableProjectId(current) != GetStableProjectId(item))
        {
            // The current object now belongs to a different project identity (its primary version changed). The
            // captured decision, source key and coordination key no longer describe it, so it is refused and
            // re-discovered in the next round from the current library state.
            return false;
        }

        try
        {
            var folders = _libraryManager.GetCollectionFolders(current);
            return folders.Any(folder => scopeLibraryIds.Contains(folder.Id));
        }
        catch (Exception)
        {
            // An item that is no longer resolvable to a collection folder is no longer in scope.
            return false;
        }
    }

    /// <summary>
    /// Gets the stable project identity used by the batch: the native primary version id when present, otherwise
    /// the item id. It matches the project key used for the fingerprint and the coordinator.
    /// </summary>
    internal static Guid GetStableProjectId(BaseItem item)
    {
        return item is Video video && video.PrimaryVersionId is { } primaryVersionId
            ? primaryVersionId
            : item.Id;
    }

    public BaseItem? GetCurrentItem(BaseItem item)
    {
        try
        {
            return _libraryManager.GetItemById(item.Id);
        }
        catch (Exception)
        {
            return null;
        }
    }
}
