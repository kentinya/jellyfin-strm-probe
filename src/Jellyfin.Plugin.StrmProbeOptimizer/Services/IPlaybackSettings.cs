namespace Jellyfin.Plugin.StrmProbeOptimizer.Services;

public interface IPlaybackSettings
{
    bool PlaybackAutoCheck { get; }
}

public sealed class PluginPlaybackSettings : IPlaybackSettings
{
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
}
