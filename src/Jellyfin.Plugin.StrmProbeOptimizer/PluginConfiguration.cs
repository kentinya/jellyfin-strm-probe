using MediaBrowser.Model.Plugins;

namespace Jellyfin.Plugin.StrmProbeOptimizer;

public sealed class PluginConfiguration : BasePluginConfiguration
{
    public const int DefaultMaxConcurrentProbes = 2;

    public const int MinMaxConcurrentProbes = 1;

    public const int MaxMaxConcurrentProbes = 8;

    /// <summary>
    /// Gets or sets a value indicating whether STRM optimization is enabled at all.
    /// </summary>
    public bool Enabled { get; set; } = true;

    /// <summary>
    /// Gets or sets a value indicating whether the playback entry point performs the automatic check.
    /// </summary>
    public bool PlaybackAutoCheck { get; set; } = true;

    /// <summary>
    /// Gets or sets the global limit for plugin initiated probes. It is captured on server start.
    /// </summary>
    public int MaxConcurrentProbes { get; set; } = DefaultMaxConcurrentProbes;

    /// <summary>
    /// Gets or sets a value indicating whether verbose diagnostic logging is enabled.
    /// </summary>
    public bool DetailedLog { get; set; }

    /// <summary>
    /// Validates the configuration without mutating it.
    /// </summary>
    /// <param name="configuration">The candidate configuration.</param>
    /// <returns>An actionable error message, or <c>null</c> when the configuration is valid.</returns>
    public static string? Validate(PluginConfiguration configuration)
    {
        ArgumentNullException.ThrowIfNull(configuration);
        if (configuration.MaxConcurrentProbes < MinMaxConcurrentProbes
            || configuration.MaxConcurrentProbes > MaxMaxConcurrentProbes)
        {
            return $"MaxConcurrentProbes must be an integer between {MinMaxConcurrentProbes} and {MaxMaxConcurrentProbes} inclusive, but the request contained {configuration.MaxConcurrentProbes}.";
        }

        return null;
    }
}
