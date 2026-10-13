using MediaBrowser.Common.Plugins;
using MediaBrowser.Common.Configuration;
using MediaBrowser.Model.Plugins;
using MediaBrowser.Model.Serialization;
using Microsoft.Extensions.Logging;

namespace Jellyfin.Plugin.StrmProbeOptimizer;

public sealed class Plugin : BasePlugin<PluginConfiguration>
{
    private readonly ILogger<Plugin> _logger;

    public Plugin(IApplicationPaths applicationPaths, IXmlSerializer xmlSerializer, ILogger<Plugin> logger)
        : base(applicationPaths, xmlSerializer)
    {
        _logger = logger;
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
    /// Validates the candidate configuration, persists it, and only then publishes it in memory.
    /// A failed save therefore leaves the previous effective configuration untouched.
    /// </summary>
    /// <param name="configuration">The candidate configuration.</param>
    public override void UpdateConfiguration(BasePluginConfiguration configuration)
    {
        ArgumentNullException.ThrowIfNull(configuration);
        if (configuration is not PluginConfiguration pluginConfiguration)
        {
            throw new ArgumentException($"The plugin configuration must be a {nameof(PluginConfiguration)}.", nameof(configuration));
        }

        var error = PluginConfiguration.Validate(pluginConfiguration);
        if (error is not null)
        {
            throw new ArgumentException(error, nameof(configuration));
        }

        // Persist first. BasePluginOfT.UpdateConfiguration replaces the in-memory value before saving,
        // which would leave an unsaved configuration effective when serialization fails.
        SaveConfiguration(pluginConfiguration);
        Configuration = pluginConfiguration;
        ConfigurationChanged?.Invoke(this, pluginConfiguration);
    }

    private int ResolveStartupMaxConcurrentProbes()
    {
        var error = PluginConfiguration.Validate(Configuration);
        if (error is null)
        {
            return Configuration.MaxConcurrentProbes;
        }

        _logger.LogError(
            "The persisted STRM Probe Optimizer configuration is invalid: {ValidationError} Using the default concurrency of {DefaultConcurrency} until the server is restarted with a corrected configuration. Edit {ConfigurationPath} or re-save the plugin configuration through Jellyfin and restart.",
            error,
            PluginConfiguration.DefaultMaxConcurrentProbes,
            ConfigurationFilePath);
        return PluginConfiguration.DefaultMaxConcurrentProbes;
    }
}
