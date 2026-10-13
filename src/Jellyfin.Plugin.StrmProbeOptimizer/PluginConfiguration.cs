using MediaBrowser.Model.Plugins;

namespace Jellyfin.Plugin.StrmProbeOptimizer;

public sealed class PluginConfiguration : BasePluginConfiguration
{
    public bool PlaybackAutoCheck { get; set; } = true;
}
