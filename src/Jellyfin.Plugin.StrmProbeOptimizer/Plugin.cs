using MediaBrowser.Common.Plugins;
using MediaBrowser.Common.Configuration;
using MediaBrowser.Model.Serialization;

namespace Jellyfin.Plugin.StrmProbeOptimizer;

public sealed class Plugin : BasePlugin<PluginConfiguration>
{
    public Plugin(IApplicationPaths applicationPaths, IXmlSerializer xmlSerializer)
        : base(applicationPaths, xmlSerializer)
    {
        Instance = this;
    }

    public static Plugin? Instance { get; private set; }

    public override string Name => "STRM Probe Optimizer";

    public override string Description => "Validates a Jellyfin-native STRM playback interception prototype.";
}
