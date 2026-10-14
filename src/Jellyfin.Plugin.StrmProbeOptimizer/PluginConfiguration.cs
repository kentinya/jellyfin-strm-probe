using System.Globalization;
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
    /// Gets or sets a value indicating whether the batch check covers every media library. A missing value in an
    /// older configuration file defaults to <c>true</c>, so legacy configurations keep the documented all-library scope.
    /// </summary>
    public bool BatchAllLibraries { get; set; } = true;

    /// <summary>
    /// Gets or sets the explicitly selected batch media library identifiers as a comma separated list of stable
    /// Jellyfin library GUIDs. It is only consulted when <see cref="BatchAllLibraries"/> is <c>false</c>.
    /// </summary>
    public string BatchLibraryIds { get; set; } = string.Empty;

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

        if (configuration.BatchAllLibraries)
        {
            return null;
        }

        if (!TryParseLibraryIds(configuration.BatchLibraryIds, out var parsed))
        {
            return "An explicit batch library selection may only contain valid Jellyfin library identifiers.";
        }

        if (parsed.Count == 0)
        {
            return "An explicit batch library selection must contain at least one valid Jellyfin library identifier; an empty selection is not silently widened to all libraries.";
        }

        return null;
    }

    /// <summary>
    /// Parses the configured batch library identifiers into a stable, ordered, de-duplicated set. Every entry must
    /// parse as a Jellyfin library GUID; a malformed entry makes the whole selection invalid so it can never be
    /// silently widened to all libraries.
    /// </summary>
    /// <param name="value">The comma separated identifier list.</param>
    /// <param name="libraryIds">The parsed stable identifiers.</param>
    /// <returns><c>true</c> when every non-empty entry parsed.</returns>
    public static bool TryParseLibraryIds(string? value, out IReadOnlyList<Guid> libraryIds)
    {
        var result = new List<Guid>();
        var seen = new HashSet<Guid>();
        if (!string.IsNullOrWhiteSpace(value))
        {
            foreach (var entry in value.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
            {
                if (!Guid.TryParse(entry, CultureInfo.InvariantCulture, out var id))
                {
                    libraryIds = [];
                    return false;
                }

                if (seen.Add(id))
                {
                    result.Add(id);
                }
            }
        }

        libraryIds = result;
        return true;
    }
}
