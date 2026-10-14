namespace Jellyfin.Plugin.StrmProbeOptimizer.Services;

public interface IPlaybackSettings
{
    bool Enabled { get; }

    bool PlaybackAutoCheck { get; }

    bool DetailedLog { get; }

    /// <summary>
    /// Gets the concurrency limit captured when the server started. Saved changes apply after the next restart.
    /// </summary>
    int MaxConcurrentProbes { get; }

    /// <summary>
    /// Gets a value indicating whether the batch check covers every media library.
    /// </summary>
    bool BatchAllLibraries { get; }

    /// <summary>
    /// Gets the explicitly selected batch media library identifiers, or an empty string for the all-library default.
    /// </summary>
    string BatchLibraryIds { get; }
}

public sealed class PluginPlaybackSettings : IPlaybackSettings
{
    public bool Enabled
    {
        get
        {
            try
            {
                return Plugin.Instance?.Configuration.Enabled ?? false;
            }
            catch
            {
                return false;
            }
        }
    }

    public bool PlaybackAutoCheck
    {
        get
        {
            try
            {
                return Plugin.Instance?.Configuration.PlaybackAutoCheck ?? false;
            }
            catch
            {
                return false;
            }
        }
    }

    public bool DetailedLog
    {
        get
        {
            try
            {
                return Plugin.Instance?.Configuration.DetailedLog ?? false;
            }
            catch
            {
                return false;
            }
        }
    }

    public int MaxConcurrentProbes
    {
        get
        {
            try
            {
                return Plugin.Instance?.StartupMaxConcurrentProbes ?? PluginConfiguration.DefaultMaxConcurrentProbes;
            }
            catch
            {
                return PluginConfiguration.DefaultMaxConcurrentProbes;
            }
        }
    }

    public bool BatchAllLibraries
    {
        get
        {
            try
            {
                return Plugin.Instance?.Configuration.BatchAllLibraries ?? true;
            }
            catch
            {
                return true;
            }
        }
    }

    public string BatchLibraryIds
    {
        get
        {
            try
            {
                return Plugin.Instance?.Configuration.BatchLibraryIds ?? string.Empty;
            }
            catch
            {
                return string.Empty;
            }
        }
    }
}
