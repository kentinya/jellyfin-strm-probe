using Jellyfin.Plugin.StrmProbeOptimizer.Interceptors;
using Jellyfin.Plugin.StrmProbeOptimizer.Services;
using MediaBrowser.Controller.Library;
using MediaBrowser.Controller.MediaEncoding;
using MediaBrowser.Controller.Persistence;
using MediaBrowser.Controller.Plugins;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;

namespace Jellyfin.Plugin.StrmProbeOptimizer;

public sealed class ServiceRegistrator : IPluginServiceRegistrator
{
    public void RegisterServices(IServiceCollection serviceCollection, MediaBrowser.Controller.IServerApplicationHost applicationHost)
    {
        ArgumentNullException.ThrowIfNull(serviceCollection);
        ArgumentNullException.ThrowIfNull(applicationHost);

        var mediaSourceRegistration = CoreServiceRegistration.ValidateCoreService(
            serviceCollection,
            typeof(IMediaSourceManager));
        var mediaEncoderRegistration = CoreServiceRegistration.ValidateCoreService(
            serviceCollection,
            typeof(IMediaEncoder));
        var mediaStreamRepositoryRegistration = CoreServiceRegistration.ValidateCoreService(
            serviceCollection,
            typeof(IMediaStreamRepository));
        var itemPersistenceRegistration = CoreServiceRegistration.ValidateCoreService(
            serviceCollection,
            typeof(IItemPersistenceService));

        serviceCollection.AddSingleton<IStrmManifestReader, StrmManifestReader>();
        serviceCollection.AddSingleton<IProbeDecisionService, ProbeDecisionService>();
        serviceCollection.AddSingleton<IStrmFingerprintRepository, SqliteStrmFingerprintRepository>();
        serviceCollection.AddSingleton<IPlaybackSettings, PluginPlaybackSettings>();
        serviceCollection.AddSingleton<ILibraryIdProvider, LibraryIdProvider>();
        serviceCollection.AddSingleton<StrmPlaybackOptimizer>();
        serviceCollection.AddSingleton<IBatchScopeResolver, BatchScopeResolver>();
        serviceCollection.AddSingleton<IBatchCandidateSource, LibraryBatchCandidateSource>();
        // The batch runner must drive the real native media source manager, never the proxy: a batch probe is a
        // real native call, and routing it through the playback proxy would re-enter the playback entry point.
        serviceCollection.AddSingleton(provider => new BatchCheckRunner(
            provider.GetRequiredService<StrmPlaybackOptimizer>(),
            provider.GetRequiredService<IBatchScopeResolver>(),
            provider.GetRequiredService<IBatchCandidateSource>(),
            (IMediaSourceManager)provider.GetRequiredService(mediaSourceRegistration.ImplementationType),
            provider.GetRequiredService<IPlaybackSettings>(),
            provider.GetRequiredService<ILogger<BatchCheckRunner>>()));
        CoreServiceRegistration.RehomeImplementation(serviceCollection, mediaEncoderRegistration);
        CoreServiceRegistration.RehomeImplementation(serviceCollection, mediaSourceRegistration);
        CoreServiceRegistration.RehomeImplementation(serviceCollection, mediaStreamRepositoryRegistration);
        CoreServiceRegistration.RehomeImplementation(serviceCollection, itemPersistenceRegistration);
        serviceCollection.Add(ServiceDescriptor.Describe(
            typeof(IMediaEncoder),
            provider => MediaEncoderDispatchProxy.Create((IMediaEncoder)provider.GetRequiredService(mediaEncoderRegistration.ImplementationType)),
            mediaEncoderRegistration.Lifetime));
        serviceCollection.Add(ServiceDescriptor.Describe(
            typeof(IMediaSourceManager),
            provider => MediaSourceManagerDispatchProxy.Create(
                (IMediaSourceManager)provider.GetRequiredService(mediaSourceRegistration.ImplementationType),
                provider.GetRequiredService<StrmPlaybackOptimizer>()),
            mediaSourceRegistration.Lifetime));
        serviceCollection.Add(ServiceDescriptor.Describe(
            typeof(IMediaStreamRepository),
            provider => ProbePersistenceDispatchProxy.Create(
                (IMediaStreamRepository)provider.GetRequiredService(mediaStreamRepositoryRegistration.ImplementationType)),
            mediaStreamRepositoryRegistration.Lifetime));
        serviceCollection.Add(ServiceDescriptor.Describe(
            typeof(IItemPersistenceService),
            provider => ProbePersistenceDispatchProxy.Create(
                (IItemPersistenceService)provider.GetRequiredService(itemPersistenceRegistration.ImplementationType)),
            itemPersistenceRegistration.Lifetime));
    }
}

internal sealed record RehomedCoreService(ServiceDescriptor OriginalDescriptor, Type ImplementationType, ServiceLifetime Lifetime);

internal static class CoreServiceRegistration
{
    public static RehomedCoreService ValidateCoreService(IServiceCollection services, Type serviceType)
    {
        var matches = services.Where(descriptor => descriptor.ServiceType == serviceType).ToArray();
        if (matches.Length != 1)
        {
            throw new InvalidOperationException($"Expected one core registration for {serviceType.Name}, found {matches.Length}.");
        }

        var original = matches[0];
        if (original.ImplementationType is not { IsClass: true, IsAbstract: false } implementationType
            || !serviceType.IsAssignableFrom(implementationType))
        {
            throw new InvalidOperationException($"The core registration for {serviceType.Name} is not a concrete implementation type.");
        }

        if (services.Any(descriptor => descriptor.ServiceType == implementationType))
        {
            throw new InvalidOperationException($"The native implementation {implementationType.Name} is already registered separately.");
        }

        return new RehomedCoreService(original, implementationType, original.Lifetime);
    }

    public static void RehomeImplementation(IServiceCollection services, RehomedCoreService registration)
    {
        if (!services.Contains(registration.OriginalDescriptor)
            || services.Any(descriptor => descriptor.ServiceType == registration.ImplementationType))
        {
            throw new InvalidOperationException($"The core registration for {registration.ImplementationType.Name} changed after validation.");
        }

        services.Remove(registration.OriginalDescriptor);
        services.Add(ServiceDescriptor.Describe(
            registration.ImplementationType,
            registration.ImplementationType,
            registration.Lifetime));
    }

    public static RehomedCoreService MoveImplementationToConcreteService(IServiceCollection services, Type serviceType)
    {
        var registration = ValidateCoreService(services, serviceType);
        RehomeImplementation(services, registration);
        return registration;
    }
}
