using System.Reflection;
using Jellyfin.Plugin.StrmProbeOptimizer.Interceptors;
using Jellyfin.Plugin.StrmProbeOptimizer.Services;
using MediaBrowser.Controller.MediaEncoding;
using MediaBrowser.Model.Dto;
using MediaBrowser.Model.Entities;
using MediaBrowser.Model.MediaInfo;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace Jellyfin.Plugin.StrmProbeOptimizer.Tests;

[TestClass]
public sealed class ProbeExecutionContextTests
{
    [TestMethod]
    public async Task EncoderProxyObservesOnlyMatchingNativeResultWithRequiredStream()
    {
        const string expectedUrl = "https://media.example.invalid/video.mp4?sig=a";
        var native = NativeEncoder.Create();
        native.Result = new MediaInfo { MediaStreams = [new MediaStream { Type = MediaStreamType.Video }] };
        var proxy = MediaEncoderDispatchProxy.Create(native.Interface);
        using var context = ProbeExecutionContext.Begin(Guid.NewGuid(), expectedUrl, MediaStreamType.Video);

        await proxy.GetMediaInfo(Request(expectedUrl), CancellationToken.None);
        await proxy.GetMediaInfo(Request("https://media.example.invalid/other.mp4"), CancellationToken.None);

        Assert.AreEqual(1, context.MatchingCallCount);
        Assert.IsTrue(context.HasSuccessfulPrimaryResult);
    }

    [TestMethod]
    public async Task EncoderProxyCountsMatchingFailureWithoutMarkingSuccess()
    {
        const string expectedUrl = "https://media.example.invalid/video.mp4?sig=a";
        var native = NativeEncoder.Create();
        native.Failure = new IOException("test fixture failure");
        var proxy = MediaEncoderDispatchProxy.Create(native.Interface);
        using var context = ProbeExecutionContext.Begin(Guid.NewGuid(), expectedUrl, MediaStreamType.Video);

        await AssertThrowsAsync<IOException>(() => proxy.GetMediaInfo(Request(expectedUrl), CancellationToken.None));

        Assert.AreEqual(1, context.MatchingCallCount);
        Assert.IsFalse(context.HasSuccessfulPrimaryResult);
    }

    private static MediaInfoRequest Request(string path)
    {
        return new MediaInfoRequest { MediaSource = new MediaSourceInfo { Path = path } };
    }

    private static async Task<TException> AssertThrowsAsync<TException>(Func<Task> action)
        where TException : Exception
    {
        try
        {
            await action();
        }
        catch (TException exception)
        {
            return exception;
        }

        throw new AssertFailedException($"Expected {typeof(TException).Name}.");
    }

    public class NativeEncoder : DispatchProxy
    {
        public IMediaEncoder Interface { get; private set; } = null!;

        public MediaInfo Result { get; set; } = new();

        public Exception? Failure { get; set; }

        public static NativeEncoder Create()
        {
            var proxy = DispatchProxy.Create<IMediaEncoder, NativeEncoder>();
            var native = (NativeEncoder)(object)proxy;
            native.Interface = proxy;
            return native;
        }

        protected override object? Invoke(MethodInfo? targetMethod, object?[]? args)
        {
            if (targetMethod?.Name == nameof(IMediaEncoder.GetMediaInfo))
            {
                return Failure is null
                    ? Task.FromResult(Result)
                    : Task.FromException<MediaInfo>(Failure);
            }

            return null;
        }
    }
}
