using System.Reflection;
using Jellyfin.Plugin.StrmProbeOptimizer.Interceptors;
using Jellyfin.Plugin.StrmProbeOptimizer.Services;
using MediaBrowser.Controller.Library;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace Jellyfin.Plugin.StrmProbeOptimizer.Tests;

[TestClass]
public sealed class MediaSourceManagerProxyTests
{
    [TestMethod]
    public void ProxyDelegatesEveryInterfaceMethod()
    {
        var native = NativeManager.Create();
        var optimizer = new StrmPlaybackOptimizer(
            new StrmManifestReader(),
            new ProbeDecisionService(),
            new InMemoryStrmFingerprintRepository(),
            new TestPlaybackSettings(),
            NullLogger<StrmPlaybackOptimizer>.Instance);
        var proxy = MediaSourceManagerDispatchProxy.Create(native.Interface, optimizer);

        foreach (var method in typeof(IMediaSourceManager).GetMethods())
        {
            var arguments = method.GetParameters().Select(parameter =>
            {
                var type = parameter.ParameterType;
                if (type == typeof(CancellationToken))
                {
                    return (object?)CancellationToken.None;
                }

                return type.IsValueType ? Activator.CreateInstance(type) : null;
            }).ToArray();
            method.Invoke(proxy, arguments);
        }

        Assert.AreEqual(typeof(IMediaSourceManager).GetMethods().Length, native.Calls);
    }

    private sealed class TestPlaybackSettings : IPlaybackSettings
    {
        public bool Enabled => true;

        public bool PlaybackAutoCheck => false;

        public bool DetailedLog => false;

        public int MaxConcurrentProbes => PluginConfiguration.DefaultMaxConcurrentProbes;
    }

    public class NativeManager : DispatchProxy
    {
        public IMediaSourceManager Interface { get; private set; } = null!;

        public int Calls { get; private set; }

        public static NativeManager Create()
        {
            var proxy = DispatchProxy.Create<IMediaSourceManager, NativeManager>();
            var native = (NativeManager)(object)proxy;
            native.Interface = proxy;
            return native;
        }

        protected override object? Invoke(MethodInfo? targetMethod, object?[]? args)
        {
            Calls++;
            return DefaultReturn(targetMethod!.ReturnType);
        }

        private static object? DefaultReturn(Type returnType)
        {
            if (returnType == typeof(void))
            {
                return null;
            }

            if (returnType == typeof(Task))
            {
                return Task.CompletedTask;
            }

            if (returnType.IsGenericType && returnType.GetGenericTypeDefinition() == typeof(Task<>))
            {
                var resultType = returnType.GenericTypeArguments[0];
                var value = resultType.IsValueType ? Activator.CreateInstance(resultType) : null;
                return typeof(Task).GetMethod(nameof(Task.FromResult))!.MakeGenericMethod(resultType).Invoke(null, [value]);
            }

            return returnType.IsValueType ? Activator.CreateInstance(returnType) : null;
        }
    }
}
