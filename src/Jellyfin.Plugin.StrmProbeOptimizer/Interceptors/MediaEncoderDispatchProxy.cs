using System.Reflection;
using System.Runtime.ExceptionServices;
using Jellyfin.Plugin.StrmProbeOptimizer.Services;
using MediaBrowser.Controller.MediaEncoding;
using MediaBrowser.Model.MediaInfo;

namespace Jellyfin.Plugin.StrmProbeOptimizer.Interceptors;

public class MediaEncoderDispatchProxy : DispatchProxy
{
    private IMediaEncoder? _native;

    public static IMediaEncoder Create(IMediaEncoder native)
    {
        var proxy = DispatchProxy.Create<IMediaEncoder, MediaEncoderDispatchProxy>();
        ((MediaEncoderDispatchProxy)(object)proxy)._native = native;
        return proxy;
    }

    protected override object? Invoke(MethodInfo? targetMethod, object?[]? args)
    {
        if (targetMethod is null || _native is null)
        {
            throw new InvalidOperationException("The native media encoder proxy is not initialized.");
        }

        if (targetMethod.Name != nameof(IMediaEncoder.GetMediaInfo)
            || args is not { Length: > 0 }
            || args[0] is not MediaInfoRequest request
            || ProbeExecutionContext.Current is not { } context)
        {
            return InvokeNative(targetMethod, args);
        }

        var requestedPath = request.MediaSource?.Path;
        context.MarkCall(requestedPath);
        var result = InvokeNative(targetMethod, args);
        return result is Task<MediaInfo> mediaInfoTask
            ? ObserveAsync(mediaInfoTask, requestedPath, context)
            : result;
    }

    private object? InvokeNative(MethodInfo method, object?[]? args)
    {
        try
        {
            return method.Invoke(_native, args);
        }
        catch (TargetInvocationException exception) when (exception.InnerException is not null)
        {
            ExceptionDispatchInfo.Capture(exception.InnerException).Throw();
            throw;
        }
    }

    private static async Task<MediaInfo> ObserveAsync(Task<MediaInfo> mediaInfoTask, string? requestedPath, ProbeExecutionContext context)
    {
        var result = await mediaInfoTask.ConfigureAwait(false);
        context.RecordResult(requestedPath, result);
        return result;
    }
}
