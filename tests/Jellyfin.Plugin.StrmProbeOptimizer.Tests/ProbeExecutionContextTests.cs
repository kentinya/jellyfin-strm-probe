using System.Reflection;
using System.Text.Json;
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
    public void VerifiedNativeReadbackMayOmitColorRangeButNotChangeOtherIdentityFields()
    {
        var itemId = Guid.NewGuid();
        const string url = "https://media.example.invalid/video.mp4";
        using var context = ProbeExecutionContext.Begin(itemId, url, MediaStreamType.Video);
        var encoded = new MediaStream { Type = MediaStreamType.Video, Index = 0, Codec = "h264", Width = 320, ColorRange = "tv" };
        context.RecordResult(url, new MediaInfo { MediaStreams = [encoded] });
        context.RecordPersistedMediaStreams(itemId, [encoded]);

        Assert.IsTrue(context.IsPersistedProbeResult(new MediaStream { Type = MediaStreamType.Video, Index = 0, Codec = "h264", Width = 320 }));
        Assert.IsFalse(context.IsPersistedProbeResult(new MediaStream { Type = MediaStreamType.Video, Index = 0, Codec = "h264", Width = 640 }));
        Assert.IsFalse(context.IsPersistedProbeResult(new MediaStream { Type = MediaStreamType.Video, Index = 1, Codec = "h264", Width = 320 }));
        Assert.IsFalse(context.IsPersistedProbeResult(new MediaStream { Type = MediaStreamType.Video, Index = 0, Codec = "h264", Width = 320, ColorRange = "pc" }));
    }

    [TestMethod]
    public void MissingReadbackColorRangeDoesNotBypassTheExactSuccessfulSaveSignal()
    {
        var itemId = Guid.NewGuid();
        const string url = "https://media.example.invalid/video.mp4";
        using var context = ProbeExecutionContext.Begin(itemId, url, MediaStreamType.Video);
        var encoded = new MediaStream { Type = MediaStreamType.Video, Codec = "h264", ColorRange = "tv" };
        var readback = new MediaStream { Type = MediaStreamType.Video, Codec = "h264" };
        context.RecordResult(url, new MediaInfo { MediaStreams = [encoded] });

        Assert.IsFalse(context.IsPersistedProbeResult(readback));
        context.RecordPersistedMediaStreams(itemId, [readback]);
        Assert.IsFalse(context.HasPersistedPrimaryResult);
        Assert.IsFalse(context.IsPersistedProbeResult(readback));
        context.RecordPersistedMediaStreams(Guid.NewGuid(), [encoded]);
        Assert.IsFalse(context.HasPersistedPrimaryResult);
    }

    [TestMethod]
    public void DiagnosticSnapshotsDescribeTheThreeNativeStagesWithoutRequestSecrets()
    {
        var itemId = Guid.NewGuid();
        const string url = "https://media.example.invalid/video.mp4?token=private-test-token";
        var observed = new List<(string Stage, string Fields)>();
        using var context = ProbeExecutionContext.Begin(
            itemId, itemId, itemId.ToString("N"), url, MediaStreamType.Video,
            onPrimaryStreamObserved: (stage, fields) => observed.Add((stage, fields)));
        var stream = new MediaStream
        {
            Type = MediaStreamType.Video,
            Codec = "h264",
            Index = 0,
            Width = 320,
            Height = 180,
            ColorRange = "tv",
            Path = "/private/media/path",
        };

        context.RecordResult(url, new MediaInfo { MediaStreams = [stream] });
        context.RecordPersistedMediaStreams(itemId, [stream]);
        Assert.IsTrue(context.IsPersistedProbeResult(stream));

        CollectionAssert.AreEqual(new[] { "encoder", "saved", "returned" }, observed.Select(entry => entry.Stage).ToArray());
        foreach (var (_, fields) in observed)
        {
            using var document = JsonDocument.Parse(fields);
            Assert.AreEqual(33, document.RootElement.EnumerateObject().Count());
            Assert.AreEqual("tv", document.RootElement.GetProperty("ColorRange").GetString());
            Assert.IsFalse(fields.Contains("private-test-token", StringComparison.Ordinal));
            Assert.IsFalse(fields.Contains("/private/media/path", StringComparison.Ordinal));
            Assert.IsFalse(fields.Contains(url, StringComparison.Ordinal));
        }
    }

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
