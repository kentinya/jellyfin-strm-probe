using MediaBrowser.Common.Plugins;
using MediaBrowser.Common.Configuration;
using MediaBrowser.Model.Plugins;
using MediaBrowser.Model.Serialization;
using Microsoft.Extensions.Logging;
using Jellyfin.Plugin.StrmProbeOptimizer.Services;

namespace Jellyfin.Plugin.StrmProbeOptimizer;

public sealed class Plugin : BasePlugin<PluginConfiguration>, IHasWebPages
{
    private readonly ILogger<Plugin> _logger;
    private readonly ILibraryIdProvider? _libraryIdProvider;

    public Plugin(
        IApplicationPaths applicationPaths,
        IXmlSerializer xmlSerializer,
        ILogger<Plugin> logger,
        ILibraryIdProvider? libraryIdProvider = null)
        : base(applicationPaths, xmlSerializer)
    {
        _logger = logger;
        _libraryIdProvider = libraryIdProvider;
        Instance = this;
        StartupMaxConcurrentProbes = ResolveStartupMaxConcurrentProbes();
        _logger.LogInformation(
            "STRM Probe Optimizer initialized: enabled {Enabled}, playbackAutoCheck {PlaybackAutoCheck}, detailedLog {DetailedLog}, global probe concurrency {MaxConcurrentProbes}. Saved concurrency changes apply after the next server restart.",
            Configuration.Enabled,
            Configuration.PlaybackAutoCheck,
            Configuration.DetailedLog,
            StartupMaxConcurrentProbes);
    }

    public static Plugin? Instance { get; private set; }

    /// <summary>
    /// Gets the concurrency limit captured when the server started. Configuration changes only apply after a restart.
    /// </summary>
    public int StartupMaxConcurrentProbes { get; }

    public override string Name => "STRM Probe Optimizer";

    public override string Description => "Validates a Jellyfin-native STRM playback interception prototype.";

    /// <summary>
    /// Exposes the plugin's own configuration page through Jellyfin's standard plugin page mechanism. Jellyfin's
    /// dashboard controller reads the embedded resource by name, so the page is served from the plugin assembly
    /// without any separate web host or configuration service.
    /// </summary>
    /// <returns>The single configuration page descriptor.</returns>
    public IEnumerable<PluginPageInfo> GetPages()
    {
        return
        [
            new PluginPageInfo
            {
                Name = ConfigurationPageName,
                EmbeddedResourcePath = GetType().Namespace + ".Configuration.configPage.html"
            }
        ];
    }

    /// <summary>
    /// Gets the stable page name used by Jellyfin's <c>web/ConfigurationPage</c> endpoint.
    /// </summary>
    internal const string ConfigurationPageName = "StrmProbeOptimizer";

    /// <summary>
    /// Validates the candidate configuration, persists it atomically, and only then publishes it in memory.
    /// A failed save therefore leaves the previous effective configuration and the previously saved file untouched.
    /// </summary>
    /// <param name="configuration">The candidate configuration.</param>
    public override void UpdateConfiguration(BasePluginConfiguration configuration)
    {
        ArgumentNullException.ThrowIfNull(configuration);
        if (configuration is not PluginConfiguration pluginConfiguration)
        {
            throw new ArgumentException($"The plugin configuration must be a {nameof(PluginConfiguration)}.", nameof(configuration));
        }

        var availableLibraryIds = ResolveAvailableLibraryIds();
        if (!pluginConfiguration.BatchAllLibraries && availableLibraryIds is null)
        {
            // The library id provider is unavailable. Fail closed instead of silently persisting a scope that
            // could reference a library that no longer exists.
            throw new ArgumentException("The batch media library selection cannot be verified because the library catalog is unavailable; retry after the server has finished starting.", nameof(configuration));
        }

        var error = PluginConfiguration.Validate(pluginConfiguration, availableLibraryIds);
        if (error is not null)
        {
            throw new ArgumentException(error, nameof(configuration));
        }

        // Persist first, and atomically: the native SaveConfiguration serializes straight into the live file
        // with FileMode.Create, so a mid-write failure would truncate the previously valid configuration.
        SaveConfigurationAtomically(pluginConfiguration);
        Configuration = pluginConfiguration;
        ConfigurationChanged?.Invoke(this, pluginConfiguration);
    }

    /// <summary>
    /// Serializes the candidate to a temporary file in the plugin configuration directory and only replaces the
    /// live configuration file after the complete candidate has been written. A serialization failure leaves the
    /// previous file and the previous in-memory configuration in place.
    /// </summary>
    private void SaveConfigurationAtomically(PluginConfiguration configuration)
    {
        var directory = ApplicationPaths.PluginConfigurationsPath;
        Directory.CreateDirectory(directory);
        var temporaryPath = Path.Combine(directory, ConfigurationFileName + ".tmp-" + Guid.NewGuid().ToString("N"));

        try
        {
            XmlSerializer.SerializeToFile(configuration, temporaryPath);
            File.Move(temporaryPath, ConfigurationFilePath, overwrite: true);
        }
        catch
        {
            try
            {
                if (File.Exists(temporaryPath))
                {
                    File.Delete(temporaryPath);
                }
            }
            catch (IOException)
            {
                // Best effort cleanup; the original configuration file is left untouched.
            }

            throw;
        }
    }

    private IReadOnlyCollection<Guid>? ResolveAvailableLibraryIds()
    {
        return _libraryIdProvider?.GetAvailableLibraryIds();
    }

    private int ResolveStartupMaxConcurrentProbes()
    {
        var error = PluginConfiguration.Validate(Configuration);
        if (error is null)
        {
            return Configuration.MaxConcurrentProbes;
        }

        _logger.LogError(
            "The persisted STRM Probe Optimizer configuration is invalid: {ValidationError} Using the default concurrency of {DefaultConcurrency} until the server is restarted with a corrected configuration. Re-save the plugin configuration through Jellyfin (plugin id {PluginId}) and restart.",
            error,
            PluginConfiguration.DefaultMaxConcurrentProbes,
            Id);
        return PluginConfiguration.DefaultMaxConcurrentProbes;
    }
}
