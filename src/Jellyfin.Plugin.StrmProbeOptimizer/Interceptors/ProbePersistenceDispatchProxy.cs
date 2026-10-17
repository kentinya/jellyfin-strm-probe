using System.Reflection;
using System.Runtime.ExceptionServices;
using Jellyfin.Plugin.StrmProbeOptimizer.Services;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Persistence;
using MediaBrowser.Model.Entities;

namespace Jellyfin.Plugin.StrmProbeOptimizer.Interceptors;

public class ProbePersistenceDispatchProxy : DispatchProxy
{
    private object? _native;

    public static T Create<T>(T native)
        where T : class
    {
        ArgumentNullException.ThrowIfNull(native);
        var proxy = DispatchProxy.Create<T, ProbePersistenceDispatchProxy>();
        ((ProbePersistenceDispatchProxy)(object)proxy)._native = native;
        return proxy;
    }

    protected override object? Invoke(MethodInfo? targetMethod, object?[]? args)
    {
        if (targetMethod is null || _native is null)
        {
            throw new InvalidOperationException("The native persistence proxy is not initialized.");
        }

        var result = InvokeNative(targetMethod, args);
        var context = ProbeExecutionContext.Current;
        if (context is null || args is null)
        {
            return result;
        }

        if (targetMethod.Name == nameof(IMediaStreamRepository.SaveMediaStreams)
            && args is [Guid itemId, IReadOnlyList<MediaStream> streams, _])
        {
            context.RecordPersistedMediaStreams(itemId, streams);
        }
        else if (targetMethod.Name == nameof(IItemPersistenceService.SaveItems)
            && args is [IReadOnlyList<BaseItem> items, _])
        {
            foreach (var item in items)
            {
                context.RecordPersistedItem(item);
            }
        }

        return result;
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
}
