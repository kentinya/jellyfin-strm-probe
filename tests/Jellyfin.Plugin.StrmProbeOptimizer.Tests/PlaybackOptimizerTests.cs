using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using Jellyfin.Plugin.StrmProbeOptimizer.Services;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Entities.TV;
using MediaBrowser.Controller.Library;
using MediaBrowser.Model.Dto;
using MediaBrowser.Model.Entities;
using MediaBrowser.Model.MediaInfo;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace Jellyfin.Plugin.StrmProbeOptimizer.Tests;

[TestClass]
public sealed class PlaybackOptimizerTests
{
    private const string ValidSha1 = "0123456789abcdef0123456789abcdef01234567";

    [TestMethod]
    public async Task SameUrlAndShaSkipsNativeRefresh()
    {
        const string url = "https://media.example.invalid/video.mp4?sig=a";
        using var fixture = new ManifestFixture(url, ValidSha1, 42);
        var manifest = new StrmManifestReader().Read(fixture.Path).Manifest!;
        var repository = new InMemoryStrmFingerprintRepository();
        var item = CreateItem(fixture.Path, url);
        var native = ScriptedManager.Create();
        native.StaticSources = [Source(url)];
        native.Playback = (_, _, _, _) => Task.FromResult<IReadOnlyList<MediaSourceInfo>>([Source(url)]);
        repository.TryCommit(Fingerprint(item.Id, manifest), expectedPrevious: null);
        var optimizer = CreateOptimizer(repository);

        var result = await optimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, null, true, false, CancellationToken.None);

        Assert.AreEqual(1, native.PlaybackCalls);
        Assert.IsFalse(native.LastAllowMediaProbe);
        Assert.AreEqual(url, result[0].Path);
        Assert.AreEqual(manifest.UrlHash, repository.Get(item.Id, "primary")!.UrlHash);
    }

    [TestMethod]
    public async Task UrlChangeWithSameShaProbesAndCommitsOnlyAfterSavedPrimaryResult()
    {
        const string oldUrl = "https://media.example.invalid/video.mp4?sig=old";
        const string newUrl = "https://media.example.invalid/video.mp4?sig=new";
        using var fixture = new ManifestFixture(oldUrl, ValidSha1, 42);
        var reader = new StrmManifestReader();
        var oldManifest = reader.Read(fixture.Path).Manifest!;
        var repository = new InMemoryStrmFingerprintRepository();
        var item = CreateItem(fixture.Path, oldUrl);
        repository.TryCommit(Fingerprint(item.Id, oldManifest), expectedPrevious: null);
        fixture.Write(newUrl, ValidSha1, 42);
        var newManifest = reader.Read(fixture.Path).Manifest!;
        var native = ScriptedManager.Create();
        native.StaticSources = [Source(oldUrl)];
        native.Playback = (updatedItem, allowProbe, _, _) =>
        {
            Assert.IsTrue(allowProbe);
            ProbeExecutionContext.Current!.MarkCall(newUrl);
            ProbeExecutionContext.Current.RecordResult(newUrl, MediaInfoWithVideo());
            updatedItem.ShortcutPath = newUrl;
            native.StaticSources = [Source(newUrl)];
            return Task.FromResult<IReadOnlyList<MediaSourceInfo>>([Source(newUrl)]);
        };
        var optimizer = CreateOptimizer(repository);

        var result = await optimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, null, true, false, CancellationToken.None);

        Assert.AreEqual(1, native.PlaybackCalls);
        Assert.IsTrue(native.LastAllowMediaProbe);
        Assert.AreEqual(newUrl, result[0].Path);
        Assert.AreEqual(newUrl, item.ShortcutPath);
        Assert.AreEqual(newManifest.UrlHash, repository.Get(item.Id, "primary")!.UrlHash);
    }

    [TestMethod]
    public async Task FailedProbeDoesNotReplaceTheAcceptedFingerprint()
    {
        const string oldUrl = "https://media.example.invalid/video.mp4?sig=old";
        const string newUrl = "https://media.example.invalid/video.mp4?sig=new";
        using var fixture = new ManifestFixture(oldUrl, ValidSha1, 42);
        var reader = new StrmManifestReader();
        var oldManifest = reader.Read(fixture.Path).Manifest!;
        var repository = new InMemoryStrmFingerprintRepository();
        var item = CreateItem(fixture.Path, oldUrl);
        var oldFingerprint = Fingerprint(item.Id, oldManifest);
        repository.TryCommit(oldFingerprint, expectedPrevious: null);
        fixture.Write(newUrl, new string('f', 40), 99);
        var native = ScriptedManager.Create();
        native.StaticSources = [Source(oldUrl)];
        native.Playback = (_, allowProbe, _, _) =>
        {
            Assert.IsTrue(allowProbe);
            return Task.FromResult<IReadOnlyList<MediaSourceInfo>>([Source(oldUrl)]);
        };
        var optimizer = CreateOptimizer(repository);

        await AssertThrowsAsync<InvalidOperationException>(() => optimizer.GetPlaybackMediaSourcesAsync(
            native.Interface, item, null, true, false, CancellationToken.None));

        Assert.AreEqual(oldFingerprint, repository.Get(item.Id, "primary"));
    }

    [TestMethod]
    public async Task ChangedAddressCannotReturnOldStreamsWithoutAnObservedProbeResult()
    {
        const string oldUrl = "https://media.example.invalid/video.mp4?sig=old";
        const string newUrl = "https://media.example.invalid/video.mp4?sig=new";
        using var fixture = new ManifestFixture(oldUrl, ValidSha1, 42);
        var reader = new StrmManifestReader();
        var oldManifest = reader.Read(fixture.Path).Manifest!;
        var repository = new InMemoryStrmFingerprintRepository();
        var item = CreateItem(fixture.Path, oldUrl);
        var oldFingerprint = Fingerprint(item.Id, oldManifest);
        repository.TryCommit(oldFingerprint, expectedPrevious: null);
        fixture.Write(newUrl, ValidSha1, 42);
        var native = ScriptedManager.Create();
        native.StaticSources = [Source(oldUrl)];
        native.Playback = (updatedItem, allowProbe, _, _) =>
        {
            Assert.IsTrue(allowProbe);
            updatedItem.ShortcutPath = newUrl;
            return Task.FromResult<IReadOnlyList<MediaSourceInfo>>([Source(newUrl)]);
        };
        var optimizer = CreateOptimizer(repository);

        await AssertThrowsAsync<InvalidOperationException>(() => optimizer.GetPlaybackMediaSourcesAsync(
            native.Interface, item, null, true, false, CancellationToken.None));

        Assert.AreEqual(oldFingerprint, repository.Get(item.Id, "primary"));
    }

    [TestMethod]
    public async Task SuccessfulProbeWithoutSavedNewAddressDoesNotCommitOrReturnTheOldAddress()
    {
        const string oldUrl = "https://media.example.invalid/video.mp4?sig=old";
        const string newUrl = "https://media.example.invalid/video.mp4?sig=new";
        using var fixture = new ManifestFixture(oldUrl, ValidSha1, 42);
        var reader = new StrmManifestReader();
        var oldManifest = reader.Read(fixture.Path).Manifest!;
        var repository = new InMemoryStrmFingerprintRepository();
        var item = CreateItem(fixture.Path, oldUrl);
        var oldFingerprint = Fingerprint(item.Id, oldManifest);
        repository.TryCommit(oldFingerprint, expectedPrevious: null);
        fixture.Write(newUrl, ValidSha1, 42);
        var native = ScriptedManager.Create();
        native.StaticSources = [Source(oldUrl)];
        native.Playback = (_, allowProbe, _, _) =>
        {
            Assert.IsTrue(allowProbe);
            ProbeExecutionContext.Current!.MarkCall(newUrl);
            ProbeExecutionContext.Current.RecordResult(newUrl, MediaInfoWithVideo());
            return Task.FromResult<IReadOnlyList<MediaSourceInfo>>([Source(oldUrl)]);
        };
        var optimizer = CreateOptimizer(repository);

        await AssertThrowsAsync<InvalidOperationException>(() => optimizer.GetPlaybackMediaSourcesAsync(
            native.Interface, item, null, true, false, CancellationToken.None));

        Assert.AreEqual(oldUrl, item.ShortcutPath);
        Assert.AreEqual(oldFingerprint, repository.Get(item.Id, "primary"));
    }

    [TestMethod]
    public async Task FailedSameUrlProbeKeepsTheOldSavedStreamAndFingerprint()
    {
        const string url = "https://media.example.invalid/video.mp4?sig=stable";
        using var fixture = new ManifestFixture(url, ValidSha1, 42);
        var reader = new StrmManifestReader();
        var oldManifest = reader.Read(fixture.Path).Manifest!;
        var repository = new InMemoryStrmFingerprintRepository();
        var item = CreateItem(fixture.Path, url);
        var oldFingerprint = Fingerprint(item.Id, oldManifest);
        repository.TryCommit(oldFingerprint, expectedPrevious: null);
        fixture.Write(url, new string('f', 40), 99);
        var native = ScriptedManager.Create();
        native.StaticSources = [Source(url)];
        native.Playback = (_, allowProbe, _, _) =>
        {
            Assert.IsTrue(allowProbe);
            return Task.FromResult<IReadOnlyList<MediaSourceInfo>>([Source(url)]);
        };
        var optimizer = CreateOptimizer(repository);

        var result = await optimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, null, true, false, CancellationToken.None);

        Assert.AreEqual(url, result[0].Path);
        Assert.AreEqual(oldFingerprint, repository.Get(item.Id, "primary"));
    }

    [TestMethod]
    public async Task CancellationDoesNotReplaceTheAcceptedFingerprint()
    {
        const string url = "https://media.example.invalid/video.mp4?sig=stable";
        using var fixture = new ManifestFixture(url, ValidSha1, 42);
        var reader = new StrmManifestReader();
        var oldManifest = reader.Read(fixture.Path).Manifest!;
        var repository = new InMemoryStrmFingerprintRepository();
        var item = CreateItem(fixture.Path, url);
        var oldFingerprint = Fingerprint(item.Id, oldManifest);
        repository.TryCommit(oldFingerprint, expectedPrevious: null);
        fixture.Write(url, new string('f', 40), 99);
        var native = ScriptedManager.Create();
        native.StaticSources = [Source(url)];
        using var cancellation = new CancellationTokenSource();
        var probeStarted = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        native.Playback = async (_, allowProbe, _, token) =>
        {
            Assert.IsTrue(allowProbe);
            probeStarted.TrySetResult();
            await Task.Delay(Timeout.Infinite, token);
            return [];
        };
        var optimizer = CreateOptimizer(repository);

        var pending = optimizer.GetPlaybackMediaSourcesAsync(
            native.Interface, item, null, true, false, cancellation.Token);
        await probeStarted.Task;
        cancellation.Cancel();
        await AssertThrowsAsync<TaskCanceledException>(() => pending);

        Assert.AreEqual(oldFingerprint, repository.Get(item.Id, "primary"));
    }

    [TestMethod]
    public async Task ManifestChangedDuringProbeDoesNotCommitAnOldResult()
    {
        const string oldUrl = "https://media.example.invalid/video.mp4?sig=old";
        const string requestedUrl = "https://media.example.invalid/video.mp4?sig=requested";
        const string latestUrl = "https://media.example.invalid/video.mp4?sig=latest";
        using var fixture = new ManifestFixture(oldUrl, ValidSha1, 42);
        var reader = new StrmManifestReader();
        var oldManifest = reader.Read(fixture.Path).Manifest!;
        var repository = new InMemoryStrmFingerprintRepository();
        var item = CreateItem(fixture.Path, oldUrl);
        var oldFingerprint = Fingerprint(item.Id, oldManifest);
        repository.TryCommit(oldFingerprint, expectedPrevious: null);
        fixture.Write(requestedUrl, ValidSha1, 42);
        var native = ScriptedManager.Create();
        native.StaticSources = [Source(oldUrl)];
        native.Playback = (updatedItem, allowProbe, _, _) =>
        {
            Assert.IsTrue(allowProbe);
            ProbeExecutionContext.Current!.MarkCall(requestedUrl);
            ProbeExecutionContext.Current.RecordResult(requestedUrl, MediaInfoWithVideo());
            updatedItem.ShortcutPath = requestedUrl;
            fixture.Write(latestUrl, ValidSha1, 42);
            return Task.FromResult<IReadOnlyList<MediaSourceInfo>>([Source(requestedUrl)]);
        };
        var optimizer = CreateOptimizer(repository);

        await AssertThrowsAsync<InvalidOperationException>(() => optimizer.GetPlaybackMediaSourcesAsync(
            native.Interface, item, null, true, false, CancellationToken.None));

        Assert.AreEqual(oldFingerprint, repository.Get(item.Id, "primary"));
    }

    [TestMethod]
    public async Task DisallowedProbeIsPassedThroughWithoutReadingOrCommitting()
    {
        const string url = "https://media.example.invalid/video.mp4?sig=a";
        using var fixture = new ManifestFixture(url, ValidSha1, 42);
        var repository = new InMemoryStrmFingerprintRepository();
        var item = CreateItem(fixture.Path, url);
        var native = ScriptedManager.Create();
        native.Playback = (_, allowProbe, _, _) =>
        {
            Assert.IsFalse(allowProbe);
            return Task.FromResult<IReadOnlyList<MediaSourceInfo>>([Source(url)]);
        };
        var optimizer = CreateOptimizer(repository);

        await optimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, null, false, false, CancellationToken.None);

        Assert.AreEqual(0, native.StaticCalls);
        Assert.IsNull(repository.Get(item.Id, "primary"));
    }

    [TestMethod]
    public async Task DisabledOptimizerDelegatesOriginalProbePermission()
    {
        const string url = "https://media.example.invalid/video.mp4?sig=a";
        using var fixture = new ManifestFixture(url, ValidSha1, 42);
        var repository = new InMemoryStrmFingerprintRepository();
        var item = CreateItem(fixture.Path, url);
        var native = ScriptedManager.Create();
        native.StaticSources = [Source(url)];
        native.Playback = (_, allowProbe, _, _) =>
        {
            Assert.IsTrue(allowProbe);
            return Task.FromResult<IReadOnlyList<MediaSourceInfo>>([Source(url)]);
        };
        var optimizer = new StrmPlaybackOptimizer(
            new StrmManifestReader(),
            new ProbeDecisionService(),
            repository,
            new PlaybackSettings(false),
            NullLogger<StrmPlaybackOptimizer>.Instance);

        await optimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, null, true, false, CancellationToken.None);

        Assert.AreEqual(0, native.StaticCalls);
        Assert.AreEqual(1, native.PlaybackCalls);
        Assert.IsTrue(native.LastAllowMediaProbe);
        Assert.IsNull(repository.Get(item.Id, "primary"));
    }

    [TestMethod]
    public async Task LegacyStrmDelegatesOriginalProbePermission()
    {
        const string url = "https://media.example.invalid/legacy.mp4?sig=a";
        var path = System.IO.Path.Combine(System.IO.Path.GetTempPath(), $"strm-probe-{Guid.NewGuid():N}.strm");
        File.WriteAllText(path, url + "\n", Encoding.UTF8);
        try
        {
            var repository = new InMemoryStrmFingerprintRepository();
            var item = CreateItem(path, url);
            var native = ScriptedManager.Create();
            native.StaticSources = [Source(url)];
            native.Playback = (_, allowProbe, _, _) =>
            {
                Assert.IsTrue(allowProbe);
                return Task.FromResult<IReadOnlyList<MediaSourceInfo>>([Source(url)]);
            };
            var optimizer = CreateOptimizer(repository);

            var result = await optimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, null, true, false, CancellationToken.None);

            Assert.AreEqual(1, native.PlaybackCalls);
            Assert.AreEqual(0, native.StaticCalls);
            Assert.IsTrue(native.LastAllowMediaProbe);
            Assert.AreEqual(url, result[0].Path);
            Assert.IsNull(repository.Get(item.Id, "primary"));
        }
        finally
        {
            File.Delete(path);
        }
    }

    [TestMethod]
    public async Task OrdinaryMediaDelegatesOriginalProbePermission()
    {
        const string url = "https://media.example.invalid/video.mp4?sig=a";
        var item = new Video { Id = Guid.NewGuid(), Path = "/media/video.mp4", ShortcutPath = url };
        var repository = new InMemoryStrmFingerprintRepository();
        var native = ScriptedManager.Create();
        native.StaticSources = [Source(url)];
        native.Playback = (_, allowProbe, _, _) =>
        {
            Assert.IsTrue(allowProbe);
            return Task.FromResult<IReadOnlyList<MediaSourceInfo>>([Source(url)]);
        };
        var optimizer = CreateOptimizer(repository);

        await optimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, null, true, false, CancellationToken.None);

        Assert.AreEqual(1, native.PlaybackCalls);
        Assert.AreEqual(0, native.StaticCalls);
        Assert.IsTrue(native.LastAllowMediaProbe);
        Assert.IsNull(repository.Get(item.Id, "primary"));
    }

    [TestMethod]
    public async Task DisallowedProbeDoesNotAcceptAChangedAddressOrFingerprint()
    {
        const string oldUrl = "https://media.example.invalid/video.mp4?sig=old";
        const string newUrl = "https://media.example.invalid/video.mp4?sig=new";
        using var fixture = new ManifestFixture(oldUrl, ValidSha1, 42);
        var reader = new StrmManifestReader();
        var oldManifest = reader.Read(fixture.Path).Manifest!;
        var repository = new InMemoryStrmFingerprintRepository();
        var item = CreateItem(fixture.Path, oldUrl);
        var oldFingerprint = Fingerprint(item.Id, oldManifest);
        repository.TryCommit(oldFingerprint, expectedPrevious: null);
        fixture.Write(newUrl, ValidSha1, 42);
        var native = ScriptedManager.Create();
        native.Playback = (_, allowProbe, _, _) =>
        {
            Assert.IsFalse(allowProbe);
            return Task.FromResult<IReadOnlyList<MediaSourceInfo>>([Source(oldUrl)]);
        };
        var optimizer = CreateOptimizer(repository);

        var result = await optimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, null, false, false, CancellationToken.None);

        Assert.AreEqual(oldUrl, result[0].Path);
        Assert.AreEqual(oldFingerprint, repository.Get(item.Id, "primary"));
        Assert.AreEqual(0, native.StaticCalls);
    }

    [TestMethod]
    public async Task FirstTrustRequiresAnExistingPrimaryStreamAndCurrentAddress()
    {
        const string url = "https://media.example.invalid/video.mp4?sig=a";
        using var fixture = new ManifestFixture(url, ValidSha1, 42);
        var repository = new InMemoryStrmFingerprintRepository();
        var item = CreateItem(fixture.Path, url);
        var native = ScriptedManager.Create();
        native.StaticSources = [Source(url)];
        native.Playback = (_, allowProbe, _, _) =>
        {
            Assert.IsFalse(allowProbe);
            return Task.FromResult<IReadOnlyList<MediaSourceInfo>>([Source(url)]);
        };
        var optimizer = CreateOptimizer(repository);

        await optimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, null, true, false, CancellationToken.None);

        Assert.IsNotNull(repository.Get(item.Id, "primary"));
        Assert.AreEqual(0, native.LastAllowMediaProbe ? 1 : 0);
    }

    private static StrmPlaybackOptimizer CreateOptimizer(IStrmFingerprintRepository repository)
    {
        return new StrmPlaybackOptimizer(
            new StrmManifestReader(),
            new ProbeDecisionService(),
            repository,
            new PlaybackSettings(true),
            NullLogger<StrmPlaybackOptimizer>.Instance);
    }

    private static Video CreateItem(string path, string url)
    {
        return new Video { Id = Guid.NewGuid(), Path = path, ShortcutPath = url };
    }

    private static MediaSourceInfo Source(string url)
    {
        return new MediaSourceInfo
        {
            Path = url,
            MediaStreams = [new MediaStream { Type = MediaStreamType.Video }]
        };
    }

    private static MediaInfo MediaInfoWithVideo()
    {
        return new MediaInfo
        {
            MediaStreams = [new MediaStream { Type = MediaStreamType.Video }]
        };
    }

    private static StrmFingerprint Fingerprint(Guid itemId, StrmManifest manifest)
    {
        return new StrmFingerprint(itemId, "primary", manifest.UrlHash, manifest.Sha1, manifest.Size);
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

    private sealed record PlaybackSettings(bool PlaybackAutoCheck) : IPlaybackSettings;

    private sealed class ManifestFixture : IDisposable
    {
        public ManifestFixture(string url, string? sha1, long? size)
        {
            Path = System.IO.Path.Combine(System.IO.Path.GetTempPath(), $"strm-probe-{Guid.NewGuid():N}.strm");
            Write(url, sha1, size);
        }

        public string Path { get; }

        public void Write(string url, string? sha1, long? size)
        {
            var lines = new List<string> { "# strm-probe-version:1" };
            if (sha1 is not null)
            {
                lines.Add($"# strm-probe-sha1:{sha1}");
            }

            if (size.HasValue)
            {
                lines.Add($"# strm-probe-size:{size.Value}");
            }

            lines.Add(url);
            File.WriteAllText(Path, string.Join('\n', lines) + "\n", Encoding.UTF8);
        }

        public void Dispose()
        {
            File.Delete(Path);
        }
    }

    public class ScriptedManager : DispatchProxy
    {
        private Func<BaseItem, bool, bool, CancellationToken, Task<IReadOnlyList<MediaSourceInfo>>>? _playback;

        public IMediaSourceManager Interface { get; private set; } = null!;

        public int StaticCalls { get; private set; }

        public int PlaybackCalls { get; private set; }

        public bool LastAllowMediaProbe { get; private set; }

        public IReadOnlyList<MediaSourceInfo> StaticSources { get; set; } = [];

        public Func<BaseItem, bool, bool, CancellationToken, Task<IReadOnlyList<MediaSourceInfo>>>? Playback
        {
            get => _playback;
            set => _playback = value;
        }

        public static ScriptedManager Create()
        {
            var proxy = DispatchProxy.Create<IMediaSourceManager, ScriptedManager>();
            var fake = (ScriptedManager)(object)proxy;
            fake.Interface = proxy;
            return fake;
        }

        protected override object? Invoke(MethodInfo? targetMethod, object?[]? args)
        {
            if (targetMethod is null)
            {
                throw new InvalidOperationException("Missing interface method.");
            }

            if (targetMethod.Name == nameof(IMediaSourceManager.GetStaticMediaSources))
            {
                StaticCalls++;
                return StaticSources;
            }

            if (targetMethod.Name == nameof(IMediaSourceManager.GetPlaybackMediaSources) && args is { Length: 5 })
            {
                PlaybackCalls++;
                var item = (BaseItem)args[0]!;
                var allowProbe = (bool)args[2]!;
                LastAllowMediaProbe = allowProbe;
                return _playback?.Invoke(item, allowProbe, (bool)args[3]!, (CancellationToken)args[4]!)
                    ?? Task.FromResult(StaticSources);
            }

            return DefaultReturn(targetMethod.ReturnType);
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
