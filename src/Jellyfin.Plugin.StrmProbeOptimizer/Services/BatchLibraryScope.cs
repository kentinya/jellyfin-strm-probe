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

        try
        {
            // Re-read the current object through the native library instead of trusting the stale candidate. A
            // candidate that was deleted, moved out of the selected libraries or changed type while it was queued
            // must not be probed from a stale object, so admission verifies the current native identity and
            // relationship rather than only the captured object's parent chain.
            var current = _libraryManager.GetItemById(item.Id);
            if (current is null || current.GetType() != item.GetType())
            {
                return false;
            }

            var folders = _libraryManager.GetCollectionFolders(current);
            return folders.Any(folder => scopeLibraryIds.Contains(folder.Id));
        }
        catch (Exception)
        {
            // An item that is no longer resolvable to a collection folder is no longer in scope.
            return false;
        }
    }
}
