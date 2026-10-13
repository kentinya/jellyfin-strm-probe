using Jellyfin.Plugin.StrmProbeOptimizer;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace Jellyfin.Plugin.StrmProbeOptimizer.Tests;

[TestClass]
public sealed class CoreServiceRegistrationTests
{
    [TestMethod]
    public void RehomedNativeSingletonIsCreatedAndDisposedExactlyOnce()
    {
        NativeService.Created = 0;
        NativeService.Disposed = 0;
        var services = new ServiceCollection();
        services.AddSingleton<INativeService, NativeService>();
        var registration = CoreServiceRegistration.MoveImplementationToConcreteService(services, typeof(INativeService));
        ((IServiceCollection)services).Add(ServiceDescriptor.Describe(
            typeof(INativeService),
            provider => new NativeServiceDecorator((INativeService)provider.GetRequiredService(registration.ImplementationType)),
            registration.Lifetime));

        using (var provider = services.BuildServiceProvider())
        {
            var decorated = (NativeServiceDecorator)provider.GetRequiredService<INativeService>();
            var native = (INativeService)provider.GetRequiredService(registration.ImplementationType);
            Assert.AreSame(native, decorated.Inner);
            Assert.AreEqual(1, NativeService.Created);
            Assert.AreEqual(0, NativeService.Disposed);
        }

        Assert.AreEqual(1, NativeService.Disposed);
    }

    private interface INativeService
    {
    }

    private sealed class NativeService : INativeService, IDisposable
    {
        public static int Created { get; set; }

        public static int Disposed { get; set; }

        public NativeService()
        {
            Created++;
        }

        public void Dispose()
        {
            Disposed++;
        }
    }

    private sealed class NativeServiceDecorator(INativeService inner) : INativeService
    {
        public INativeService Inner { get; } = inner;
    }
}
