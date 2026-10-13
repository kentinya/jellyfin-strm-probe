using System.Reflection;
using System.Runtime.ExceptionServices;
using Jellyfin.Plugin.StrmProbeOptimizer.Services;
using Jellyfin.Database.Implementations.Entities;
using MediaBrowser.Controller.Library;
using MediaBrowser.Model.Dto;

namespace Jellyfin.Plugin.StrmProbeOptimizer.Interceptors;

public class MediaSourceManagerDispatchProxy : DispatchProxy
{
    private IMediaSourceManager? _native;
    private StrmPlaybackOptimizer? _optimizer;

    public static IMediaSourceManager Create(IMediaSourceManager native, StrmPlaybackOptimizer optimizer)
    {
        var proxy = DispatchProxy.Create<IMediaSourceManager, MediaSourceManagerDispatchProxy>();
        var dispatchProxy = (MediaSourceManagerDispatchProxy)(object)proxy;
        dispatchProxy._native = native;
        dispatchProxy._optimizer = optimizer;
        return proxy;
    }

    protected override object? Invoke(MethodInfo? targetMethod, object?[]? args)
    {
        if (targetMethod is null || _native is null || _optimizer is null)
        {
            throw new InvalidOperationException("The native media source manager proxy is not initialized.");
        }

        if (targetMethod.Name == nameof(IMediaSourceManager.GetPlaybackMediaSources)
            && args is { Length: 5 }
            && args[0] is MediaBrowser.Controller.Entities.BaseItem item
            && args[2] is bool allowMediaProbe
            && args[3] is bool enablePathSubstitution
            && args[4] is CancellationToken cancellationToken)
        {
            return _optimizer.GetPlaybackMediaSourcesAsync(
                _native,
                item,
                args[1] as User,
                allowMediaProbe,
                enablePathSubstitution,
                cancellationToken);
        }

        try
        {
            return targetMethod.Invoke(_native, args);
        }
        catch (TargetInvocationException exception) when (exception.InnerException is not null)
        {
            ExceptionDispatchInfo.Capture(exception.InnerException).Throw();
            throw;
        }
    }
}
