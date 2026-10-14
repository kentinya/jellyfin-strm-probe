using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using Jellyfin.Database.Implementations.Entities;
using Jellyfin.Plugin.StrmProbeOptimizer.Interceptors;
using Jellyfin.Plugin.StrmProbeOptimizer.Services;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Entities.Audio;
using MediaBrowser.Controller.Entities.TV;
using MediaBrowser.Controller.Library;
using MediaBrowser.Controller.Persistence;
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
        Assert.AreEqual(manifest.UrlHash, repository.Get(item.Id, SourceKey(item.Id))!.UrlHash);
    }

    [TestMethod]
    public async Task ManifestChangedDuringFinalSourceReadDoesNotReturnAStalePlaybackSource()
    {
        const string url = "https://media.example.invalid/video.mp4?sig=a";
        const string changedUrl = "https://media.example.invalid/video.mp4?sig=b";
        using var fixture = new ManifestFixture(url, ValidSha1, 42);
        var manifest = new StrmManifestReader().Read(fixture.Path).Manifest!;
        var repository = new InMemoryStrmFingerprintRepository();
        var item = CreateItem(fixture.Path, url);
        repository.TryCommit(Fingerprint(item.Id, manifest), expectedPrevious: null);
        var native = ScriptedManager.Create();
        native.StaticSources = [Source(url)];
        native.OnNativeNoProbe = _ => fixture.Write(changedUrl, ValidSha1, 42);
        var optimizer = CreateOptimizer(repository);

        await AssertThrowsAsync<InvalidOperationException>(() => optimizer.GetPlaybackMediaSourcesAsync(
            native.Interface, item, null, true, false, CancellationToken.None));

        Assert.AreEqual(url, native.StaticSources[0].Path);
        Assert.AreEqual(manifest.UrlHash, repository.Get(item.Id, SourceKey(item.Id))!.UrlHash);
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
        var nativeStreamRepository = NativePersistence.Create<IMediaStreamRepository>();
        var streamRepository = ProbePersistenceDispatchProxy.Create(nativeStreamRepository);
        var nativeItemPersistence = NativePersistence.Create<IItemPersistenceService>();
        var itemPersistence = ProbePersistenceDispatchProxy.Create(nativeItemPersistence);
        native.StaticSources = [Source(oldUrl)];
        native.Playback = (updatedItem, allowProbe, _, _) =>
        {
            Assert.IsTrue(allowProbe);
            var result = MediaInfoWithVideo();
            ProbeExecutionContext.Current!.MarkCall(newUrl);
            ProbeExecutionContext.Current.RecordResult(newUrl, result);
            streamRepository.SaveMediaStreams(updatedItem.Id, result.MediaStreams, CancellationToken.None);
            updatedItem.ShortcutPath = newUrl;
            itemPersistence.SaveItems([updatedItem], CancellationToken.None);
            native.StaticSources = [Source(newUrl)];
            return Task.FromResult<IReadOnlyList<MediaSourceInfo>>([Source(newUrl)]);
        };
        var optimizer = CreateOptimizer(repository);

        var result = await optimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, null, true, false, CancellationToken.None);

        // One current-source read at admission, one actual probe and one final current-source read. Only the
        // probe call carries probe permission; the extra read is the required action-time re-evaluation.
        Assert.AreEqual(3, native.PlaybackCalls);
        Assert.IsTrue(native.LastAllowMediaProbe);
        Assert.AreEqual(newUrl, result[0].Path);
        Assert.AreEqual(newUrl, item.ShortcutPath);
        Assert.AreEqual(newManifest.UrlHash, repository.Get(item.Id, SourceKey(item.Id))!.UrlHash);
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

        Assert.AreEqual(oldFingerprint, repository.Get(item.Id, SourceKey(item.Id)));
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

        Assert.AreEqual(oldFingerprint, repository.Get(item.Id, SourceKey(item.Id)));
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
        Assert.AreEqual(oldFingerprint, repository.Get(item.Id, SourceKey(item.Id)));
    }

    [TestMethod]
    public async Task NewAddressWithOldPersistedPrimaryStreamDoesNotCommitAndRemainsRetryable()
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
        var nativeStreamRepository = NativePersistence.Create<IMediaStreamRepository>();
        var streamRepository = ProbePersistenceDispatchProxy.Create(nativeStreamRepository);
        var nativeItemPersistence = NativePersistence.Create<IItemPersistenceService>();
        var itemPersistence = ProbePersistenceDispatchProxy.Create(nativeItemPersistence);
        var staleStream = new MediaStream { Type = MediaStreamType.Video, Codec = "mpeg2video", Width = 640, Height = 360 };
        native.StaticSources = [Source(oldUrl, staleStream)];
        native.Playback = (updatedItem, allowProbe, _, _) =>
        {
            Assert.IsTrue(allowProbe);
            var result = MediaInfoWithVideo("h264", 1920, 1080);
            ProbeExecutionContext.Current!.MarkCall(newUrl);
            ProbeExecutionContext.Current.RecordResult(newUrl, result);
            streamRepository.SaveMediaStreams(updatedItem.Id, [staleStream], CancellationToken.None);
            updatedItem.ShortcutPath = newUrl;
            itemPersistence.SaveItems([updatedItem], CancellationToken.None);
            native.StaticSources = [Source(newUrl, staleStream)];
            return Task.FromResult<IReadOnlyList<MediaSourceInfo>>([Source(newUrl, staleStream)]);
        };
        var optimizer = CreateOptimizer(repository);

        await AssertThrowsAsync<InvalidOperationException>(() => optimizer.GetPlaybackMediaSourcesAsync(
            native.Interface, item, null, true, false, CancellationToken.None));

        Assert.AreEqual(oldFingerprint, repository.Get(item.Id, SourceKey(item.Id)));
        Assert.IsTrue(native.LastAllowMediaProbe);
    }

    [TestMethod]
    public void PersistenceProxyDoesNotConfirmNativeSavesThatThrow()
    {
        var itemId = Guid.NewGuid();
        const string url = "https://media.example.invalid/video.mp4?sig=new";
        var item = new Video { Id = itemId, Path = "/tmp/fixture.strm", ShortcutPath = url };
        var stream = MediaInfoWithVideo().MediaStreams[0];
        using var context = ProbeExecutionContext.Begin(itemId, url, MediaStreamType.Video);
        context.MarkCall(url);
        context.RecordResult(url, MediaInfoWithVideo());

        var failedStreamRepository = NativePersistence.Create<IMediaStreamRepository>(nameof(IMediaStreamRepository.SaveMediaStreams));
        var streamRepository = ProbePersistenceDispatchProxy.Create(failedStreamRepository);
        AssertThrows<InvalidOperationException>(() =>
            streamRepository.SaveMediaStreams(itemId, [stream], CancellationToken.None));
        Assert.IsFalse(context.HasPersistedPrimaryResult);

        var failedItemPersistence = NativePersistence.Create<IItemPersistenceService>(nameof(IItemPersistenceService.SaveItems));
        var itemPersistence = ProbePersistenceDispatchProxy.Create(failedItemPersistence);
        AssertThrows<InvalidOperationException>(() =>
            itemPersistence.SaveItems([item], CancellationToken.None));
        Assert.IsFalse(context.HasPersistedAddress);
    }

    [TestMethod]
    public async Task FailedNativeStreamSaveLeavesChangedAddressFingerprintRetryable()
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
        var failingStreamRepository = NativePersistence.Create<IMediaStreamRepository>(nameof(IMediaStreamRepository.SaveMediaStreams));
        var streamRepository = ProbePersistenceDispatchProxy.Create(failingStreamRepository);
        var itemPersistence = ProbePersistenceDispatchProxy.Create(NativePersistence.Create<IItemPersistenceService>());
        var staleStream = new MediaStream { Type = MediaStreamType.Video, Codec = "mpeg2video", Width = 640, Height = 360 };
        native.StaticSources = [Source(oldUrl, staleStream)];
        native.Playback = (updatedItem, allowProbe, _, _) =>
        {
            Assert.IsTrue(allowProbe);
            var result = MediaInfoWithVideo("h264", 1920, 1080);
            ProbeExecutionContext.Current!.MarkCall(newUrl);
            ProbeExecutionContext.Current.RecordResult(newUrl, result);
            try
            {
                streamRepository.SaveMediaStreams(updatedItem.Id, result.MediaStreams, CancellationToken.None);
            }
            catch (InvalidOperationException)
            {
                // Jellyfin providers can continue after a persistence failure; the optimizer must not infer success.
            }

            updatedItem.ShortcutPath = newUrl;
            itemPersistence.SaveItems([updatedItem], CancellationToken.None);
            return Task.FromResult<IReadOnlyList<MediaSourceInfo>>([Source(newUrl, staleStream)]);
        };
        var optimizer = CreateOptimizer(repository);

        await AssertThrowsAsync<InvalidOperationException>(() => optimizer.GetPlaybackMediaSourcesAsync(
            native.Interface, item, null, true, false, CancellationToken.None));

        Assert.AreEqual(oldFingerprint, repository.Get(item.Id, SourceKey(item.Id)));
        Assert.IsTrue(native.LastAllowMediaProbe);
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

        await AssertThrowsAsync<InvalidOperationException>(() => optimizer.GetPlaybackMediaSourcesAsync(
            native.Interface, item, null, true, false, CancellationToken.None));

        Assert.AreEqual(oldFingerprint, repository.Get(item.Id, SourceKey(item.Id)));
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

        Assert.AreEqual(oldFingerprint, repository.Get(item.Id, SourceKey(item.Id)));
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

        Assert.AreEqual(oldFingerprint, repository.Get(item.Id, SourceKey(item.Id)));
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
        Assert.IsNull(repository.Get(item.Id, SourceKey(item.Id)));
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
        Assert.IsNull(repository.Get(item.Id, SourceKey(item.Id)));
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
            Assert.IsNull(repository.Get(item.Id, SourceKey(item.Id)));
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
        Assert.IsNull(repository.Get(item.Id, SourceKey(item.Id)));
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
        native.StaticSources = [Source(oldUrl)];
        native.Playback = (_, allowProbe, _, _) =>
        {
            Assert.IsFalse(allowProbe);
            return Task.FromResult<IReadOnlyList<MediaSourceInfo>>([Source(oldUrl)]);
        };
        var optimizer = CreateOptimizer(repository);

        var result = await optimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, null, false, false, CancellationToken.None);

        Assert.AreEqual(oldUrl, result[0].Path);
        Assert.AreEqual(oldFingerprint, repository.Get(item.Id, SourceKey(item.Id)));
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

        Assert.IsNotNull(repository.Get(item.Id, SourceKey(item.Id)));
        Assert.AreEqual(0, native.LastAllowMediaProbe ? 1 : 0);
    }

    [TestMethod]
    public async Task AudioStrmRequiresAndAcceptsTheNativeAudioPrimaryStream()
    {
        const string url = "https://media.example.invalid/audio.mp3?sig=a";
        using var fixture = new ManifestFixture(url, ValidSha1, 42);
        var item = new Audio { Id = Guid.NewGuid(), Path = fixture.Path, ShortcutPath = url };
        var audioStream = new MediaStream { Type = MediaStreamType.Audio, Codec = "aac", Channels = 2, SampleRate = 44100 };
        var native = ScriptedManager.Create();
        native.StaticSources = [new MediaSourceInfo
        {
            Path = url,
            MediaStreams = [new MediaStream { Type = MediaStreamType.Video }]
        }];
        native.Playback = (sourceItem, allowProbe, _, _) =>
        {
            Assert.IsTrue(allowProbe);
            var result = new MediaInfo { MediaStreams = [audioStream] };
            ProbeExecutionContext.Current!.MarkCall(url);
            ProbeExecutionContext.Current.RecordResult(url, result);
            var streamRepository = ProbePersistenceDispatchProxy.Create(NativePersistence.Create<IMediaStreamRepository>());
            streamRepository.SaveMediaStreams(sourceItem.Id, result.MediaStreams, CancellationToken.None);
            native.StaticSources = [Source(url, audioStream)];
            return Task.FromResult<IReadOnlyList<MediaSourceInfo>>([Source(url, audioStream)]);
        };
        var repository = new InMemoryStrmFingerprintRepository();
        var optimizer = CreateOptimizer(repository);

        var resultSources = await optimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, null, true, false, CancellationToken.None);

        // One current-source read at admission, one actual probe and one final current-source read.
        Assert.AreEqual(3, native.PlaybackCalls);
        Assert.IsTrue(native.LastAllowMediaProbe);
        Assert.IsTrue(resultSources.Single().MediaStreams.Any(stream => stream.Type == MediaStreamType.Audio));
        Assert.IsNotNull(repository.Get(item.Id, SourceKey(item.Id)));
    }

    [TestMethod]
    public async Task AlternateVersionUsesItsOwnStrmProbeAndStableProjectSourceIdentity()
    {
        const string primaryUrl = "https://media.example.invalid/primary.mp4?sig=primary";
        const string alternateOldUrl = "https://media.example.invalid/alternate.mp4?sig=old";
        const string alternateNewUrl = "https://media.example.invalid/alternate.mp4?sig=new";
        using var primaryFixture = new ManifestFixture(primaryUrl, ValidSha1, 42);
        using var alternateFixture = new ManifestFixture(alternateOldUrl, ValidSha1, 42);
        var primary = CreateItem(primaryFixture.Path, primaryUrl);
        var alternate = CreateItem(alternateFixture.Path, alternateOldUrl);
        alternate.PrimaryVersionId = primary.Id;
        var reader = new StrmManifestReader();
        var repository = new InMemoryStrmFingerprintRepository();
        var primaryBaseline = Fingerprint(primary.Id, primary.Id, reader.Read(primaryFixture.Path).Manifest!);
        var alternateBaseline = Fingerprint(primary.Id, alternate.Id, reader.Read(alternateFixture.Path).Manifest!);
        repository.TryCommit(primaryBaseline, expectedPrevious: null);
        repository.TryCommit(alternateBaseline, expectedPrevious: null);

        alternateFixture.Write(alternateNewUrl, ValidSha1, 42);
        var alternateManifest = reader.Read(alternateFixture.Path).Manifest!;
        var native = ScriptedManager.Create();
        var streamRepository = ProbePersistenceDispatchProxy.Create(NativePersistence.Create<IMediaStreamRepository>());
        var itemPersistence = ProbePersistenceDispatchProxy.Create(NativePersistence.Create<IItemPersistenceService>());
        native.StaticSources = [SourceFor(alternate.Id, alternateOldUrl), SourceFor(primary.Id, primaryUrl)];
        native.Playback = (sourceItem, allowProbe, _, _) =>
        {
            Assert.IsTrue(allowProbe);
            Assert.AreEqual(alternate.Id, sourceItem.Id, "Only the changed alternate version should be probed.");
            var result = MediaInfoWithVideo("h264", 1920, 1080);
            ProbeExecutionContext.Current!.MarkCall(alternateNewUrl);
            ProbeExecutionContext.Current.RecordResult(alternateNewUrl, result);
            streamRepository.SaveMediaStreams(alternate.Id, result.MediaStreams, CancellationToken.None);
            alternate.ShortcutPath = alternateNewUrl;
            itemPersistence.SaveItems([alternate], CancellationToken.None);
            native.StaticSources = [
                SourceFor(alternate.Id, alternateNewUrl, result.MediaStreams[0]),
                SourceFor(primary.Id, primaryUrl)
            ];
            return Task.FromResult<IReadOnlyList<MediaSourceInfo>>(native.StaticSources);
        };
        var libraryManager = ItemLookup.Create(primary, alternate);
        var optimizer = CreateOptimizer(repository, libraryManager.Interface);

        var primaryEntry = await optimizer.GetPlaybackMediaSourcesAsync(native.Interface, primary, null, true, false, CancellationToken.None);

        Assert.AreEqual(2, primaryEntry.Count);
        Assert.AreEqual(3, native.PlaybackCalls, "The changed alternate source requires an admission read, the probe and the final current-source read.");
        Assert.AreEqual(alternateNewUrl, primaryEntry.Single(source => source.Id == alternate.Id.ToString("N")).Path);
        Assert.AreEqual(primaryUrl, primaryEntry.Single(source => source.Id == primary.Id.ToString("N")).Path);
        Assert.AreEqual(alternateManifest.UrlHash, repository.Get(primary.Id, SourceKey(alternate.Id))!.UrlHash);
        Assert.AreEqual(primaryBaseline, repository.Get(primary.Id, SourceKey(primary.Id)));

        // The same source ID remains the key when Jellyfin is entered through the alternate item and returns versions in another order.
        native.StaticSources = [SourceFor(primary.Id, primaryUrl), SourceFor(alternate.Id, alternateNewUrl, MediaInfoWithVideo().MediaStreams[0])];
        var directAlternateEntry = await optimizer.GetPlaybackMediaSourcesAsync(native.Interface, alternate, null, true, false, CancellationToken.None);
        var selectedAlternate = directAlternateEntry.Single(source => source.Id == alternate.Id.ToString("N"));

        Assert.AreEqual(alternateNewUrl, selectedAlternate.Path);
        Assert.AreEqual(ProbeDecisionKind.SkipProbe, DecisionKind(reader.Read(alternateFixture.Path).Manifest!, repository.Get(primary.Id, SourceKey(alternate.Id))));
        Assert.AreEqual(4, native.PlaybackCalls, "The second entry only skips, adding one final current-source read.");
    }

    [TestMethod]
    public async Task MixedLegacySourceRetainsItsNativeProbeWhileSupportedSourceIsSkipped()
    {
        const string supportedUrl = "https://media.example.invalid/supported.mp4?sig=a";
        const string legacyUrl = "https://media.example.invalid/legacy.mp4?sig=b";
        using var supportedFixture = new ManifestFixture(supportedUrl, ValidSha1, 42);
        var supported = CreateItem(supportedFixture.Path, supportedUrl);
        var legacyPath = Path.Combine(Path.GetTempPath(), $"strm-probe-{Guid.NewGuid():N}.strm");
        File.WriteAllText(legacyPath, legacyUrl + "\n", Encoding.UTF8);
        var legacy = CreateItem(legacyPath, legacyUrl);
        legacy.PrimaryVersionId = supported.Id;
        var repository = new InMemoryStrmFingerprintRepository();
        var baseline = Fingerprint(supported.Id, supported.Id, new StrmManifestReader().Read(supportedFixture.Path).Manifest!);
        repository.TryCommit(baseline, expectedPrevious: null);
        var native = ScriptedManager.Create();
        native.StaticSources = [SourceFor(supported.Id, supportedUrl), SourceFor(legacy.Id, legacyUrl)];
        var delegatedIds = new List<Guid>();
        native.Playback = (sourceItem, allowProbe, _, _) =>
        {
            if (allowProbe)
            {
                delegatedIds.Add(sourceItem.Id);
            }

            return Task.FromResult<IReadOnlyList<MediaSourceInfo>>(native.StaticSources);
        };
        var optimizer = CreateOptimizer(repository, ItemLookup.Create(supported, legacy).Interface);

        try
        {
            var result = await optimizer.GetPlaybackMediaSourcesAsync(native.Interface, supported, null, true, false, CancellationToken.None);

            Assert.AreEqual(2, result.Count);
            CollectionAssert.AreEqual(new[] { legacy.Id }, delegatedIds);
            Assert.AreEqual(baseline, repository.Get(supported.Id, SourceKey(supported.Id)));
        }
        finally
        {
            File.Delete(legacyPath);
        }
    }

    [TestMethod]
    public async Task MixedOrdinarySourceRetainsItsNativeProbeWhileSupportedSourceIsSkipped()
    {
        const string supportedUrl = "https://media.example.invalid/supported.mp4?sig=a";
        const string ordinaryUrl = "https://media.example.invalid/ordinary.mp4?sig=b";
        using var supportedFixture = new ManifestFixture(supportedUrl, ValidSha1, 42);
        var supported = CreateItem(supportedFixture.Path, supportedUrl);
        var ordinary = new Video { Id = Guid.NewGuid(), Path = "/media/ordinary.mp4", ShortcutPath = ordinaryUrl };
        ordinary.PrimaryVersionId = supported.Id;
        var repository = new InMemoryStrmFingerprintRepository();
        var baseline = Fingerprint(supported.Id, new StrmManifestReader().Read(supportedFixture.Path).Manifest!);
        repository.TryCommit(baseline, expectedPrevious: null);
        var native = ScriptedManager.Create();
        native.StaticSources = [SourceFor(supported.Id, supportedUrl), SourceFor(ordinary.Id, ordinaryUrl)];
        var delegatedIds = new List<Guid>();
        native.Playback = (sourceItem, allowProbe, _, _) =>
        {
            if (allowProbe)
            {
                delegatedIds.Add(sourceItem.Id);
            }

            return Task.FromResult<IReadOnlyList<MediaSourceInfo>>(native.StaticSources);
        };
        var optimizer = CreateOptimizer(repository, ItemLookup.Create(supported, ordinary).Interface);

        var result = await optimizer.GetPlaybackMediaSourcesAsync(native.Interface, supported, null, true, false, CancellationToken.None);

        Assert.AreEqual(2, result.Count);
        CollectionAssert.AreEqual(new[] { ordinary.Id }, delegatedIds);
        Assert.AreEqual(baseline, repository.Get(supported.Id, SourceKey(supported.Id)));
    }

    [TestMethod]
    public async Task UnresolvableVisibleSourceDelegatesTheWholeRequestToJellyfin()
    {
        const string url = "https://media.example.invalid/video.mp4?sig=a";
        using var fixture = new ManifestFixture(url, ValidSha1, 42);
        var item = CreateItem(fixture.Path, url);
        var unknownSourceId = Guid.NewGuid();
        var native = ScriptedManager.Create();
        native.StaticSources = [SourceFor(item.Id, url), SourceFor(unknownSourceId, "https://media.example.invalid/unknown.mp4")];
        var delegatedItems = new List<Guid>();
        native.Playback = (delegatedItem, allowProbe, _, _) =>
        {
            Assert.IsTrue(allowProbe);
            delegatedItems.Add(delegatedItem.Id);
            return Task.FromResult<IReadOnlyList<MediaSourceInfo>>(native.StaticSources);
        };
        var repository = new InMemoryStrmFingerprintRepository();
        var optimizer = CreateOptimizer(repository, ItemLookup.Create(item).Interface);

        var result = await optimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, null, true, false, CancellationToken.None);

        CollectionAssert.AreEqual(new[] { item.Id }, delegatedItems);
        Assert.AreEqual(2, result.Count);
        Assert.IsNull(repository.Get(item.Id, SourceKey(item.Id)));
    }

    [TestMethod]
    public async Task RepositoryReadFaultStopsOptimizationAndDelegatesWithOriginalPermission()
    {
        const string url = "https://media.example.invalid/video.mp4?sig=a";
        using var fixture = new ManifestFixture(url, ValidSha1, 42);
        var repository = new FaultInjectingFingerprintRepository();
        var item = CreateItem(fixture.Path, url);
        var native = ScriptedManager.Create();
        native.StaticSources = [Source(url)];
        native.Playback = (_, allowProbe, _, _) =>
        {
            Assert.IsTrue(allowProbe, "A read fault must not lower the caller's probe permission.");
            return Task.FromResult<IReadOnlyList<MediaSourceInfo>>([Source(url)]);
        };
        var optimizer = CreateOptimizer(repository);

        var result = await optimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, null, true, false, CancellationToken.None);

        Assert.AreEqual(1, repository.GetCalls, "The optimizer did not attempt the repository read that faulted.");
        Assert.IsTrue(native.PlaybackCalls >= 1);
        Assert.IsTrue(native.LastAllowMediaProbe);
        Assert.AreEqual(url, result[0].Path);
        Assert.AreEqual(0, repository.CommitCalls, "A read fault must not commit a fingerprint.");

        // The store is latched until restart: the next request delegates without touching the repository again.
        var callsAfterFault = native.PlaybackCalls;
        var afterFault = await optimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, null, true, false, CancellationToken.None);
        Assert.AreEqual(1, repository.GetCalls, "Optimization continued reading the failed store without a restart.");
        Assert.IsTrue(native.PlaybackCalls > callsAfterFault);
        Assert.IsTrue(native.LastAllowMediaProbe);
        Assert.AreEqual(url, afterFault[0].Path);
    }

    [TestMethod]
    public async Task RepositoryReadFaultDoesNotElevateFalsePermission()
    {
        const string url = "https://media.example.invalid/video.mp4?sig=a";
        using var fixture = new ManifestFixture(url, ValidSha1, 42);
        var repository = new FaultInjectingFingerprintRepository();
        var item = CreateItem(fixture.Path, url);
        var native = ScriptedManager.Create();
        native.StaticSources = [Source(url)];
        native.Playback = (_, allowProbe, _, _) =>
        {
            Assert.IsFalse(allowProbe, "A false-permission request must remain false after a read fault.");
            return Task.FromResult<IReadOnlyList<MediaSourceInfo>>([Source(url)]);
        };
        var optimizer = CreateOptimizer(repository);

        var result = await optimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, null, false, false, CancellationToken.None);

        Assert.AreEqual(0, repository.GetCalls, "A false-permission request must not read or commit the fingerprint store.");
        Assert.AreEqual(0, native.StaticCalls);
        Assert.AreEqual(1, native.PlaybackCalls);
        Assert.IsFalse(native.LastAllowMediaProbe);
        Assert.AreEqual(url, result[0].Path);
    }

    [TestMethod]
    public async Task RestartWithRepairedRepositoryRechecksAndCommits()
    {
        const string url = "https://media.example.invalid/video.mp4?sig=a";
        using var fixture = new ManifestFixture(url, ValidSha1, 42);
        var failingRepository = new FaultInjectingFingerprintRepository();
        var item = CreateItem(fixture.Path, url);
        var native = ScriptedManager.Create();
        native.StaticSources = [Source(url)];
        native.Playback = (_, allowProbe, _, _) =>
        {
            if (allowProbe && ProbeExecutionContext.Current is { } context)
            {
                var result = MediaInfoWithVideo("h264", 1920, 1080);
                context.MarkCall(url);
                context.RecordResult(url, result);
            }

            return Task.FromResult<IReadOnlyList<MediaSourceInfo>>([Source(url)]);
        };
        var faultedOptimizer = CreateOptimizer(failingRepository);
        await faultedOptimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, null, true, false, CancellationToken.None);
        Assert.AreEqual(0, failingRepository.CommitCalls);

        // A fresh optimizer instance represents the documented restart/re-check recovery path.
        var healthyRepository = new InMemoryStrmFingerprintRepository();
        var restartedOptimizer = CreateOptimizer(healthyRepository);
        var restarted = await restartedOptimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, null, true, false, CancellationToken.None);

        Assert.AreEqual(url, restarted[0].Path);
        Assert.IsNotNull(healthyRepository.Get(item.Id, SourceKey(item.Id)), "After restart the repaired store was not rechecked and committed.");
    }

    [TestMethod]
    public async Task RunningProbeIsSharedOnlyAfterItActuallyStarted()
    {
        const string oldUrl = "https://media.example.invalid/video.mp4?sig=old";
        const string newUrl = "https://media.example.invalid/video.mp4?sig=new";
        using var fixture = new ManifestFixture(oldUrl, ValidSha1, 42);
        var reader = new StrmManifestReader();
        var repository = new InMemoryStrmFingerprintRepository();
        var item = CreateItem(fixture.Path, oldUrl);
        repository.TryCommit(Fingerprint(item.Id, reader.Read(fixture.Path).Manifest!), expectedPrevious: null);
        fixture.Write(newUrl, ValidSha1, 42);

        using var coordinator = new ProbeCoordinator(2);
        var native = ScriptedManager.Create();
        var streamRepository = ProbePersistenceDispatchProxy.Create(NativePersistence.Create<IMediaStreamRepository>());
        var itemPersistence = ProbePersistenceDispatchProxy.Create(NativePersistence.Create<IItemPersistenceService>());
        var probeStarted = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var releaseProbe = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var probeExecutions = 0;
        native.StaticSources = [Source(oldUrl)];
        native.Playback = async (updatedItem, allowProbe, _, _) =>
        {
            Assert.IsTrue(allowProbe);
            var execution = Interlocked.Increment(ref probeExecutions);
            if (execution == 1)
            {
                // Preparation is done; the matching native call is the real start boundary.
                ProbeExecutionContext.Current!.MarkCall(newUrl);
                probeStarted.TrySetResult();
                await releaseProbe.Task;
                var result = MediaInfoWithVideo();
                ProbeExecutionContext.Current.RecordResult(newUrl, result);
                streamRepository.SaveMediaStreams(updatedItem.Id, result.MediaStreams, CancellationToken.None);
                updatedItem.ShortcutPath = newUrl;
                itemPersistence.SaveItems([updatedItem], CancellationToken.None);
                native.StaticSources = [Source(newUrl)];
            }

            return [Source(newUrl)];
        };
        var optimizer = CreateOptimizer(repository, coordinator: coordinator);

        var first = optimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, null, true, false, CancellationToken.None);
        await probeStarted.Task;
        Assert.AreEqual(1, coordinator.RunningCount, "The probe must be registered as running only after it actually started.");

        var second = optimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, null, true, false, CancellationToken.None);
        releaseProbe.TrySetResult();
        var results = await Task.WhenAll(first, second);

        Assert.AreEqual(1, probeExecutions, "A second caller must join the actually running probe instead of starting another one.");
        Assert.AreEqual(0, coordinator.RunningCount, "A finished probe must not stay registered.");
        Assert.AreEqual(0, coordinator.ActivePermits, "Every completion path must release its permit.");
        Assert.AreEqual(newUrl, results[0][0].Path);
        Assert.AreEqual(newUrl, results[1][0].Path, "A follower must re-read the current manifest and return the same usable source.");
        Assert.IsNotNull(repository.Get(item.Id, SourceKey(item.Id)));
    }

    [TestMethod]
    public async Task WaitingCallerCancellationDoesNotCancelAnAlreadyStartedProbe()
    {
        const string oldUrl = "https://media.example.invalid/video.mp4?sig=old";
        const string newUrl = "https://media.example.invalid/video.mp4?sig=new";
        using var fixture = new ManifestFixture(oldUrl, ValidSha1, 42);
        var reader = new StrmManifestReader();
        var repository = new InMemoryStrmFingerprintRepository();
        var item = CreateItem(fixture.Path, oldUrl);
        var oldFingerprint = Fingerprint(item.Id, reader.Read(fixture.Path).Manifest!);
        repository.TryCommit(oldFingerprint, expectedPrevious: null);
        fixture.Write(newUrl, ValidSha1, 42);

        using var coordinator = new ProbeCoordinator(2);
        var native = ScriptedManager.Create();
        var streamRepository = ProbePersistenceDispatchProxy.Create(NativePersistence.Create<IMediaStreamRepository>());
        var itemPersistence = ProbePersistenceDispatchProxy.Create(NativePersistence.Create<IItemPersistenceService>());
        var probeStarted = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var releaseProbe = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        native.StaticSources = [Source(oldUrl)];
        native.Playback = async (updatedItem, _, _, _) =>
        {
            ProbeExecutionContext.Current!.MarkCall(newUrl);
            probeStarted.TrySetResult();
            await releaseProbe.Task;
            var result = MediaInfoWithVideo();
            ProbeExecutionContext.Current.RecordResult(newUrl, result);
            streamRepository.SaveMediaStreams(updatedItem.Id, result.MediaStreams, CancellationToken.None);
            updatedItem.ShortcutPath = newUrl;
            itemPersistence.SaveItems([updatedItem], CancellationToken.None);
            native.StaticSources = [Source(newUrl)];
            return [Source(newUrl)];
        };
        var optimizer = CreateOptimizer(repository, coordinator: coordinator);

        using var cancellation = new CancellationTokenSource();
        var leader = optimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, null, true, false, CancellationToken.None);
        await probeStarted.Task;

        // The second caller waits for the running probe and then gives up. It must not cancel the probe.
        var joinReached = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        optimizer.SharedJoinBarrier = () => joinReached.TrySetResult();
        var waiter = optimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, null, true, false, cancellation.Token);
        await joinReached.Task.WaitAsync(TimeSpan.FromSeconds(10));
        cancellation.Cancel();
        await AssertThrowsAsync<OperationCanceledException>(() => waiter);

        releaseProbe.TrySetResult();
        var leaderResult = await leader;

        Assert.AreEqual(newUrl, leaderResult![0].Path, "An already started probe must finish even when a waiting caller exits.");
        Assert.AreEqual(newUrl, item.ShortcutPath);
        Assert.AreEqual(0, coordinator.RunningCount);
        Assert.AreEqual(0, coordinator.ActivePermits);
        Assert.IsNotNull(repository.Get(item.Id, SourceKey(item.Id)));
        Assert.AreNotEqual(oldFingerprint, repository.Get(item.Id, SourceKey(item.Id)));
    }

    [TestMethod]
    public async Task RunningProbeFailureIsSharedWithWaitingCallers()
    {
        const string oldUrl = "https://media.example.invalid/video.mp4?sig=old";
        const string newUrl = "https://media.example.invalid/video.mp4?sig=new";
        using var fixture = new ManifestFixture(oldUrl, ValidSha1, 42);
        var reader = new StrmManifestReader();
        var repository = new InMemoryStrmFingerprintRepository();
        var item = CreateItem(fixture.Path, oldUrl);
        var oldFingerprint = Fingerprint(item.Id, reader.Read(fixture.Path).Manifest!);
        repository.TryCommit(oldFingerprint, expectedPrevious: null);
        fixture.Write(newUrl, ValidSha1, 42);

        using var coordinator = new ProbeCoordinator(2);
        var native = ScriptedManager.Create();
        var probeStarted = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var releaseProbe = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        native.StaticSources = [Source(oldUrl)];
        native.Playback = async (_, _, _, _) =>
        {
            ProbeExecutionContext.Current!.MarkCall(newUrl);
            probeStarted.TrySetResult();
            await releaseProbe.Task;
            return [Source(oldUrl)];
        };
        var optimizer = CreateOptimizer(repository, coordinator: coordinator);

        var leader = optimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, null, true, false, CancellationToken.None);
        await probeStarted.Task;
        var follower = optimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, null, true, false, CancellationToken.None);
        releaseProbe.TrySetResult();

        await AssertThrowsAsync<InvalidOperationException>(() => leader);
        await AssertThrowsAsync<InvalidOperationException>(() => follower);

        Assert.AreEqual(oldFingerprint, repository.Get(item.Id, SourceKey(item.Id)), "A shared failure must retain the trusted baseline.");
        Assert.AreEqual(0, coordinator.RunningCount);
        Assert.AreEqual(0, coordinator.ActivePermits);
    }

    [TestMethod]
    public async Task FailedProbeIsNotReusedAsAnInFlightProbeByALaterCaller()
    {
        const string oldUrl = "https://media.example.invalid/video.mp4?sig=old";
        const string newUrl = "https://media.example.invalid/video.mp4?sig=new";
        using var fixture = new ManifestFixture(oldUrl, ValidSha1, 42);
        var reader = new StrmManifestReader();
        var repository = new InMemoryStrmFingerprintRepository();
        var item = CreateItem(fixture.Path, oldUrl);
        repository.TryCommit(Fingerprint(item.Id, reader.Read(fixture.Path).Manifest!), expectedPrevious: null);
        fixture.Write(newUrl, ValidSha1, 42);

        using var coordinator = new ProbeCoordinator(2);
        var native = ScriptedManager.Create();
        var probeExecutions = 0;
        native.StaticSources = [Source(oldUrl)];
        native.Playback = (_, _, _, _) =>
        {
            Interlocked.Increment(ref probeExecutions);
            return Task.FromResult<IReadOnlyList<MediaSourceInfo>>([Source(oldUrl)]);
        };
        var optimizer = CreateOptimizer(repository, coordinator: coordinator);

        await AssertThrowsAsync<InvalidOperationException>(() => optimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, null, true, false, CancellationToken.None));
        await AssertThrowsAsync<InvalidOperationException>(() => optimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, null, true, false, CancellationToken.None));

        Assert.AreEqual(2, probeExecutions, "A finished failed probe must not be cached as a running probe.");
        Assert.AreEqual(0, coordinator.RunningCount);
        Assert.AreEqual(0, coordinator.ActivePermits);
    }

    [TestMethod]
    public async Task DisabledOptimizerDelegatesWithoutStartingOrSharingAProbe()
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
        using var coordinator = new ProbeCoordinator(2);
        var optimizer = CreateOptimizer(
            repository,
            settings: new PlaybackSettings(true, Enabled: false),
            coordinator: coordinator);

        await optimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, null, true, false, CancellationToken.None);

        Assert.AreEqual(0, coordinator.RunningCount, "A disabled plugin must not register or start plugin probes.");
        Assert.AreEqual(0, coordinator.ActivePermits);
        Assert.IsNull(repository.Get(item.Id, SourceKey(item.Id)));
    }

    [TestMethod]
    public async Task PreparationIsNotRegisteredAsStartedAndIsNotSharedAsRunning()
    {
        const string oldUrl = "https://media.example.invalid/video.mp4?sig=old";
        const string newUrl = "https://media.example.invalid/video.mp4?sig=new";
        using var fixture = new ManifestFixture(oldUrl, ValidSha1, 42);
        var reader = new StrmManifestReader();
        var repository = new InMemoryStrmFingerprintRepository();
        var item = CreateItem(fixture.Path, oldUrl);
        repository.TryCommit(Fingerprint(item.Id, reader.Read(fixture.Path).Manifest!), expectedPrevious: null);
        fixture.Write(newUrl, ValidSha1, 42);

        using var coordinator = new ProbeCoordinator(2);
        var native = ScriptedManager.Create();
        var streamRepository = ProbePersistenceDispatchProxy.Create(NativePersistence.Create<IMediaStreamRepository>());
        var itemPersistence = ProbePersistenceDispatchProxy.Create(NativePersistence.Create<IItemPersistenceService>());
        var preparationReached = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var releaseProbe = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var probeExecutions = 0;
        var observedRunningDuringPreparation = -1;
        var observedPreparingDuringPreparation = -1;
        native.StaticSources = [Source(oldUrl)];
        native.Playback = async (updatedItem, allowProbe, _, _) =>
        {
            Assert.IsTrue(allowProbe);
            var execution = Interlocked.Increment(ref probeExecutions);
            if (execution == 1)
            {
                // This is native GetPlaybackMediaSources preparation, before the matching encoder call.
                observedRunningDuringPreparation = coordinator.RunningCount;
                observedPreparingDuringPreparation = coordinator.PreparingCount;
                preparationReached.TrySetResult();
                await releaseProbe.Task;
                var result = MediaInfoWithVideo();
                ProbeExecutionContext.Current!.MarkCall(newUrl);
                ProbeExecutionContext.Current.RecordResult(newUrl, result);
                streamRepository.SaveMediaStreams(updatedItem.Id, result.MediaStreams, CancellationToken.None);
                updatedItem.ShortcutPath = newUrl;
                itemPersistence.SaveItems([updatedItem], CancellationToken.None);
                native.StaticSources = [Source(newUrl)];
            }

            return [Source(newUrl)];
        };
        var optimizer = CreateOptimizer(repository, coordinator: coordinator);

        var leader = optimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, null, true, false, CancellationToken.None);
        await preparationReached.Task;
        Assert.AreEqual(0, observedRunningDuringPreparation, "Refresh preparation before the matching call must not be registered as running.");
        Assert.AreEqual(1, observedPreparingDuringPreparation, "A preparing owner must be tracked separately.");
        Assert.AreEqual(0, coordinator.RunningCount, "The preparation phase must not be shared as a running probe.");

        // A second caller may wait for the preparing owner, but it must not be reported as joining a running probe.
        var follower = optimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, null, true, false, CancellationToken.None);
        await Task.Delay(50);
        Assert.AreEqual(1, probeExecutions, "Waiting for preparation must not start a duplicate native execution.");

        releaseProbe.TrySetResult();
        var results = await Task.WhenAll(leader, follower);
        Assert.AreEqual(1, probeExecutions, "Exactly one native probe must actually execute.");
        Assert.AreEqual(newUrl, results[0][0].Path);
        Assert.AreEqual(newUrl, results[1][0].Path);
        Assert.AreEqual(0, coordinator.RunningCount);
        Assert.AreEqual(0, coordinator.PreparingCount);
        Assert.AreEqual(0, coordinator.ActivePermits);
    }

    [TestMethod]
    public async Task QueuedOwnerReReadsAcceptedVersionAndDoesNotProbeAgain()
    {
        const string oldUrl = "https://media.example.invalid/video.mp4?sig=old";
        const string newUrl = "https://media.example.invalid/video.mp4?sig=new";
        using var fixture = new ManifestFixture(oldUrl, ValidSha1, 42);
        var reader = new StrmManifestReader();
        var repository = new InMemoryStrmFingerprintRepository();
        var item = CreateItem(fixture.Path, oldUrl);
        repository.TryCommit(Fingerprint(item.Id, reader.Read(fixture.Path).Manifest!), expectedPrevious: null);
        fixture.Write(newUrl, ValidSha1, 42);

        using var coordinator = new ProbeCoordinator(1);
        var native = ScriptedManager.Create();
        var probeExecutions = 0;
        native.StaticSources = [Source(newUrl)];
        native.Playback = (_, _, _, _) =>
        {
            Interlocked.Increment(ref probeExecutions);
            return Task.FromResult<IReadOnlyList<MediaSourceInfo>>([Source(newUrl)]);
        };
        var optimizer = CreateOptimizer(repository, coordinator: coordinator);

        // Occupy the only permit with an unrelated preparing reservation so the real request queues.
        var blocker = await coordinator.AcquireAsync(Guid.NewGuid(), "unrelated-source", "unrelated", CancellationToken.None);
        var queued = optimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, null, true, false, CancellationToken.None);
        Assert.IsFalse(queued.IsCompleted, "The request must be waiting for a permit.");
        Assert.AreEqual(0, probeExecutions);

        // While queued, the same current version becomes accepted and the native address is updated.
        var oldFingerprint = repository.Get(item.Id, SourceKey(item.Id));
        var newManifest = reader.Read(fixture.Path).Manifest!;
        Assert.IsTrue(repository.TryCommit(Fingerprint(item.Id, newManifest), oldFingerprint));
        item.ShortcutPath = newUrl;
        native.StaticSources = [Source(newUrl)];

        blocker.Permit!.Release();
        var result = await queued;

        Assert.AreEqual(0, probeExecutions, "A queued owner must re-read the accepted version and not probe again.");
        Assert.IsNotNull(result, "The accepted version is reused and returned from the current native source.");
        Assert.AreEqual(newUrl, result[0].Path);
        Assert.AreEqual(0, coordinator.RunningCount);
        Assert.AreEqual(0, coordinator.ActivePermits);
    }

    [TestMethod]
    public async Task QueuedOwnerReReadsDisabledConfigurationAndDelegates()
    {
        const string oldUrl = "https://media.example.invalid/video.mp4?sig=old";
        const string newUrl = "https://media.example.invalid/video.mp4?sig=new";
        using var fixture = new ManifestFixture(oldUrl, ValidSha1, 42);
        var reader = new StrmManifestReader();
        var repository = new InMemoryStrmFingerprintRepository();
        var item = CreateItem(fixture.Path, oldUrl);
        repository.TryCommit(Fingerprint(item.Id, reader.Read(fixture.Path).Manifest!), expectedPrevious: null);
        fixture.Write(newUrl, ValidSha1, 42);

        using var coordinator = new ProbeCoordinator(1);
        var native = ScriptedManager.Create();
        var pluginProbeExecutions = 0;
        var delegatedWithProbePermission = 0;
        native.StaticSources = [Source(oldUrl)];
        native.Playback = (_, allowProbe, _, _) =>
        {
            if (allowProbe && ProbeExecutionContext.Current is not null)
            {
                Interlocked.Increment(ref pluginProbeExecutions);
            }

            if (allowProbe && ProbeExecutionContext.Current is null)
            {
                Interlocked.Increment(ref delegatedWithProbePermission);
            }

            return Task.FromResult<IReadOnlyList<MediaSourceInfo>>([Source(oldUrl)]);
        };
        var settings = new MutablePlaybackSettings();
        var optimizer = CreateOptimizer(repository, settings: settings, coordinator: coordinator);

        var blocker = await coordinator.AcquireAsync(Guid.NewGuid(), "unrelated-source", "unrelated", CancellationToken.None);
        var queued = optimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, null, true, false, CancellationToken.None);
        Assert.IsFalse(queued.IsCompleted);

        settings.Enabled = false;
        blocker.Permit!.Release();

        // The queued owner re-reads Enabled before starting and delegates with the caller's original permission.
        // The outer playback pipeline may still require a retry because the native address is stale in this fixture.
        try
        {
            await queued;
        }
        catch (InvalidOperationException)
        {
            // A native address that no longer matches the manifest requires a caller retry; the plugin must not have probed.
        }

        Assert.AreEqual(0, pluginProbeExecutions, "A queued owner must re-read Enabled and not start a plugin probe after it was disabled.");
        Assert.AreEqual(1, delegatedWithProbePermission, "The disabled queued request must delegate with the caller's original probe permission.");
        Assert.AreEqual(0, coordinator.RunningCount);
        Assert.AreEqual(0, coordinator.ActivePermits);
    }

    [TestMethod]
    public async Task QueuedOwnerReReadsChangedManifestAndProbesTheLatestVersion()
    {
        const string oldUrl = "https://media.example.invalid/video.mp4?sig=old";
        const string requestedUrl = "https://media.example.invalid/video.mp4?sig=requested";
        const string latestUrl = "https://media.example.invalid/video.mp4?sig=latest";
        using var fixture = new ManifestFixture(oldUrl, ValidSha1, 42);
        var reader = new StrmManifestReader();
        var repository = new InMemoryStrmFingerprintRepository();
        var item = CreateItem(fixture.Path, oldUrl);
        repository.TryCommit(Fingerprint(item.Id, reader.Read(fixture.Path).Manifest!), expectedPrevious: null);
        fixture.Write(requestedUrl, ValidSha1, 42);

        using var coordinator = new ProbeCoordinator(1);
        var native = ScriptedManager.Create();
        var streamRepository = ProbePersistenceDispatchProxy.Create(NativePersistence.Create<IMediaStreamRepository>());
        var itemPersistence = ProbePersistenceDispatchProxy.Create(NativePersistence.Create<IItemPersistenceService>());
        var probedUrls = new List<string>();
        native.StaticSources = [Source(oldUrl)];
        native.Playback = (updatedItem, allowProbe, _, _) =>
        {
            Assert.IsTrue(allowProbe);
            var url = reader.Read(fixture.Path).Manifest!.Url;
            probedUrls.Add(url);
            var result = MediaInfoWithVideo();
            ProbeExecutionContext.Current!.MarkCall(url);
            ProbeExecutionContext.Current.RecordResult(url, result);
            streamRepository.SaveMediaStreams(updatedItem.Id, result.MediaStreams, CancellationToken.None);
            updatedItem.ShortcutPath = url;
            itemPersistence.SaveItems([updatedItem], CancellationToken.None);
            native.StaticSources = [Source(url)];
            return Task.FromResult<IReadOnlyList<MediaSourceInfo>>([Source(url)]);
        };
        var optimizer = CreateOptimizer(repository, coordinator: coordinator);

        var blocker = await coordinator.AcquireAsync(Guid.NewGuid(), "unrelated-source", "unrelated", CancellationToken.None);
        var queued = optimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, null, true, false, CancellationToken.None);
        Assert.IsFalse(queued.IsCompleted);

        // The manifest changes to a newer URL while the request is queued.
        fixture.Write(latestUrl, ValidSha1, 42);
        blocker.Permit!.Release();

        // The queued owner must probe the latest version. Because the manifest changed after the request began,
        // the caller must retry the playback response instead of receiving a stale source.
        try
        {
            await queued;
        }
        catch (InvalidOperationException)
        {
            // Expected: the outer playback pipeline detects the manifest change and requires a retry.
        }

        Assert.AreEqual(latestUrl, probedUrls.Single(), "The queued owner must probe the latest manifest, not the one captured before queueing.");
        Assert.AreEqual(latestUrl, item.ShortcutPath);
        Assert.AreEqual(0, coordinator.RunningCount);
        Assert.AreEqual(0, coordinator.ActivePermits);
    }

    [TestMethod]
    public async Task StartedProbeCommitsEvenWhenNoCallerAwaitsAndTheWaiterCancels()
    {
        const string oldUrl = "https://media.example.invalid/video.mp4?sig=old";
        const string newUrl = "https://media.example.invalid/video.mp4?sig=new";
        using var fixture = new ManifestFixture(oldUrl, ValidSha1, 42);
        var reader = new StrmManifestReader();
        var repository = new InMemoryStrmFingerprintRepository();
        var item = CreateItem(fixture.Path, oldUrl);
        var oldFingerprint = Fingerprint(item.Id, reader.Read(fixture.Path).Manifest!);
        repository.TryCommit(oldFingerprint, expectedPrevious: null);
        fixture.Write(newUrl, ValidSha1, 42);

        using var coordinator = new ProbeCoordinator(2);
        var native = ScriptedManager.Create();
        var streamRepository = ProbePersistenceDispatchProxy.Create(NativePersistence.Create<IMediaStreamRepository>());
        var itemPersistence = ProbePersistenceDispatchProxy.Create(NativePersistence.Create<IItemPersistenceService>());
        var probeStarted = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var releaseProbe = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        native.StaticSources = [Source(oldUrl)];
        native.Playback = async (updatedItem, _, _, _) =>
        {
            ProbeExecutionContext.Current!.MarkCall(newUrl);
            probeStarted.TrySetResult();
            await releaseProbe.Task;
            var result = MediaInfoWithVideo();
            ProbeExecutionContext.Current.RecordResult(newUrl, result);
            streamRepository.SaveMediaStreams(updatedItem.Id, result.MediaStreams, CancellationToken.None);
            updatedItem.ShortcutPath = newUrl;
            itemPersistence.SaveItems([updatedItem], CancellationToken.None);
            native.StaticSources = [Source(newUrl)];
            return [Source(newUrl)];
        };
        var optimizer = CreateOptimizer(repository, coordinator: coordinator);

        // The leading caller's result is deliberately not awaited; the started probe must finish on its own.
        var leader = optimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, null, true, false, CancellationToken.None);
        await probeStarted.Task;

        // A second caller joins and then exits before the probe finishes; it must not cancel the execution.
        using var cancellation = new CancellationTokenSource();
        var joinReached = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        optimizer.SharedJoinBarrier = () => joinReached.TrySetResult();
        var waiter = optimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, null, true, false, cancellation.Token);
        await joinReached.Task.WaitAsync(TimeSpan.FromSeconds(10));
        cancellation.Cancel();
        await AssertThrowsAsync<OperationCanceledException>(() => waiter);

        releaseProbe.TrySetResult();
        var leaderResult = await leader;

        Assert.AreEqual(newUrl, leaderResult![0].Path, "An already started probe must complete even with no remaining waiters.");
        Assert.AreEqual(0, coordinator.RunningCount);
        Assert.AreEqual(0, coordinator.ActivePermits);
        var committed = repository.Get(item.Id, SourceKey(item.Id));
        Assert.IsNotNull(committed);
        Assert.AreNotEqual(oldFingerprint, committed, "The completed probe must still commit its verified fingerprint.");
    }

    [TestMethod]
    public async Task SaturatedPluginPoolDoesNotBlockNonPluginNativeWork()
    {
        const string url = "https://media.example.invalid/video.mp4?sig=a";
        using var fixture = new ManifestFixture(url, ValidSha1, 42);
        var repository = new InMemoryStrmFingerprintRepository();
        var item = new Video { Id = Guid.NewGuid(), Path = "/media/ordinary.mp4", ShortcutPath = url };
        var native = ScriptedManager.Create();
        native.StaticSources = [Source(url)];
        native.Playback = (_, allowProbe, _, _) =>
        {
            Assert.IsTrue(allowProbe);
            return Task.FromResult<IReadOnlyList<MediaSourceInfo>>([Source(url)]);
        };
        using var coordinator = new ProbeCoordinator(2);

        // Saturate the plugin pool with two running plugin probes for other keys.
        var first = await coordinator.AcquireAsync(Guid.NewGuid(), "other-a", "h", CancellationToken.None);
        var second = await coordinator.AcquireAsync(Guid.NewGuid(), "other-b", "h", CancellationToken.None);
        Assert.IsTrue(coordinator.TryMarkStarted(first.Item, out _));
        Assert.IsTrue(coordinator.TryMarkStarted(second.Item, out _));
        Assert.AreEqual(2, coordinator.ActivePermits);

        var optimizer = CreateOptimizer(repository, coordinator: coordinator);

        // Ordinary (non-plugin) native work must not wait for a plugin permit.
        var delegated = await optimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, null, true, false, CancellationToken.None)
            .WaitAsync(TimeSpan.FromSeconds(5));
        Assert.AreEqual(url, delegated[0].Path);
        Assert.AreEqual(2, coordinator.ActivePermits, "Delegated native work must not consume a plugin permit.");

        coordinator.Complete(first.Item, null);
        coordinator.Complete(second.Item, null);
        Assert.AreEqual(0, coordinator.ActivePermits);
    }

    [TestMethod]
    public async Task SharedProbeCallersKeepTheirOwnUserAndPathSubstitution()
    {
        const string oldUrl = "https://media.example.invalid/video.mp4?sig=old";
        const string newUrl = "https://media.example.invalid/video.mp4?sig=new";
        using var fixture = new ManifestFixture(oldUrl, ValidSha1, 42);
        var reader = new StrmManifestReader();
        var repository = new InMemoryStrmFingerprintRepository();
        var item = CreateItem(fixture.Path, oldUrl);
        repository.TryCommit(Fingerprint(item.Id, reader.Read(fixture.Path).Manifest!), expectedPrevious: null);
        fixture.Write(newUrl, ValidSha1, 42);

        using var coordinator = new ProbeCoordinator(2);
        var native = ScriptedManager.Create();
        var streamRepository = ProbePersistenceDispatchProxy.Create(NativePersistence.Create<IMediaStreamRepository>());
        var itemPersistence = ProbePersistenceDispatchProxy.Create(NativePersistence.Create<IItemPersistenceService>());
        var probeStarted = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var releaseProbe = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        native.StaticSources = [Source(oldUrl)];
        native.Playback = async (updatedItem, allowProbe, substitute, _) =>
        {
            if (!allowProbe)
            {
                return [Source(newUrl)];
            }

            ProbeExecutionContext.Current!.MarkCall(newUrl);
            probeStarted.TrySetResult();
            await releaseProbe.Task;
            var result = MediaInfoWithVideo();
            ProbeExecutionContext.Current.RecordResult(newUrl, result);
            streamRepository.SaveMediaStreams(updatedItem.Id, result.MediaStreams, CancellationToken.None);
            updatedItem.ShortcutPath = newUrl;
            itemPersistence.SaveItems([updatedItem], CancellationToken.None);
            native.StaticSources = [Source(newUrl)];
            return [Source(newUrl)];
        };
        var optimizer = CreateOptimizer(repository, coordinator: coordinator);

        var leader = optimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, null, true, enablePathSubstitution: true, CancellationToken.None);
        await probeStarted.Task;
        var follower = optimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, null, true, enablePathSubstitution: false, CancellationToken.None);
        releaseProbe.TrySetResult();
        var results = await Task.WhenAll(leader, follower);

        Assert.AreEqual(newUrl, results[0][0].Path);
        Assert.AreEqual(newUrl, results[1][0].Path, "The joining caller must re-read its own native source, not reuse the leader's response.");
        Assert.IsTrue(native.NoProbePathSubstitutions.Contains(false), "The follower must re-read the native source with its own path substitution value.");
        Assert.IsTrue(native.NoProbePathSubstitutions.Contains(true), "The leading caller's own path substitution must be preserved.");
    }

    [TestMethod]
    public async Task QueuedOwnerReReadsTheCurrentNativeSourceAndReusesAnAcceptedVersion()
    {
        const string oldUrl = "https://media.example.invalid/video.mp4?sig=old";
        const string newUrl = "https://media.example.invalid/video.mp4?sig=new";
        using var fixture = new ManifestFixture(oldUrl, ValidSha1, 42);
        var reader = new StrmManifestReader();
        var repository = new InMemoryStrmFingerprintRepository();
        var item = CreateItem(fixture.Path, oldUrl);
        var key = SourceKey(item.Id);
        var oldFingerprint = Fingerprint(item.Id, reader.Read(fixture.Path).Manifest!);
        repository.TryCommit(oldFingerprint, expectedPrevious: null);
        fixture.Write(newUrl, ValidSha1, 42);

        using var coordinator = new ProbeCoordinator(1);
        var native = ScriptedManager.Create();
        var probeExecutions = 0;
        var captured = Source(oldUrl);
        captured.Id = key;
        native.StaticSources = [captured];
        native.Playback = (_, _, _, _) =>
        {
            Interlocked.Increment(ref probeExecutions);
            return Task.FromResult<IReadOnlyList<MediaSourceInfo>>([Source(newUrl)]);
        };
        var optimizer = CreateOptimizer(repository, coordinator: coordinator);

        // The captured pre-queue source still points at the old URL and already has a primary stream.
        var blocker = await coordinator.AcquireAsync(Guid.NewGuid(), "unrelated-source", "unrelated", CancellationToken.None);
        var queued = optimizer.CheckSourceAsync(native.Interface, item.Id, item, captured, key, true, null, false, CancellationToken.None, isPlaybackContext: true);
        Assert.IsFalse(queued.IsCompleted, "The request must be waiting for a permit.");
        Assert.AreEqual(0, probeExecutions);

        // While queued, the current version becomes accepted and the native source moves to the new URL. Because
        // the earlier snapshot already had a primary stream, the old code kept using it and probed again.
        var newManifest = reader.Read(fixture.Path).Manifest!;
        Assert.IsTrue(repository.TryCommit(Fingerprint(item.Id, newManifest), oldFingerprint));
        item.ShortcutPath = newUrl;
        native.StaticSources = [Source(newUrl)];

        coordinator.Abandon(blocker.Item);
        var result = await queued.WaitAsync(TimeSpan.FromSeconds(10));

        Assert.AreEqual(0, probeExecutions, "A queued owner must re-read the current source and reuse the accepted version.");
        Assert.IsNull(result, "The accepted version is reused and the native source is kept.");
        Assert.AreEqual(0, coordinator.RunningCount);
        Assert.AreEqual(0, coordinator.ActivePermits);
    }

    [TestMethod]
    public async Task QueuedOwnerReReadsTheCurrentNativeSourceWhenThePrimaryStreamDisappears()
    {
        const string oldUrl = "https://media.example.invalid/video.mp4?sig=old";
        const string newUrl = "https://media.example.invalid/video.mp4?sig=new";
        using var fixture = new ManifestFixture(oldUrl, ValidSha1, 42);
        var reader = new StrmManifestReader();
        var repository = new InMemoryStrmFingerprintRepository();
        var item = CreateItem(fixture.Path, oldUrl);
        var key = SourceKey(item.Id);
        var oldFingerprint = Fingerprint(item.Id, reader.Read(fixture.Path).Manifest!);
        repository.TryCommit(oldFingerprint, expectedPrevious: null);
        fixture.Write(newUrl, ValidSha1, 42);

        using var coordinator = new ProbeCoordinator(1);
        var native = ScriptedManager.Create();
        var probeExecutions = 0;
        var captured = Source(newUrl);
        captured.Id = key;
        native.StaticSources = [captured];
        native.Playback = (_, allowProbe, _, _) =>
        {
            Assert.IsTrue(allowProbe);
            Interlocked.Increment(ref probeExecutions);
            return Task.FromResult<IReadOnlyList<MediaSourceInfo>>([Source(newUrl)]);
        };
        var optimizer = CreateOptimizer(repository, coordinator: coordinator);

        // The captured pre-queue source already points at the current URL and has a primary stream, but while the
        // request is queued the real native primary stream disappears. Reusing the stale snapshot would skip the probe.
        var blocker = await coordinator.AcquireAsync(Guid.NewGuid(), "unrelated-source", "unrelated", CancellationToken.None);
        var queued = optimizer.CheckSourceAsync(native.Interface, item.Id, item, captured, key, true, null, false, CancellationToken.None, isPlaybackContext: true);
        Assert.IsFalse(queued.IsCompleted);

        var newManifest = reader.Read(fixture.Path).Manifest!;
        Assert.IsTrue(repository.TryCommit(Fingerprint(item.Id, newManifest), oldFingerprint));
        item.ShortcutPath = newUrl;
        native.StaticSources = [new MediaSourceInfo { Id = key, Path = newUrl, MediaStreams = [] }];

        coordinator.Abandon(blocker.Item);
        try
        {
            await queued.WaitAsync(TimeSpan.FromSeconds(10));
        }
        catch (InvalidOperationException)
        {
            // The native fixture cannot persist a probe result; the required behaviour is that a probe was attempted.
        }

        Assert.AreEqual(1, probeExecutions, "A vanished current primary stream must still require a probe even when the snapshot had one.");
        Assert.AreEqual(0, coordinator.RunningCount);
        Assert.AreEqual(0, coordinator.ActivePermits);
    }

    [TestMethod]
    public async Task QueuedOwnerAdmissionDelegationFailureReleasesPermitAndRegistration()
    {
        const string oldUrl = "https://media.example.invalid/video.mp4?sig=old";
        const string newUrl = "https://media.example.invalid/video.mp4?sig=new";
        using var fixture = new ManifestFixture(oldUrl, ValidSha1, 42);
        var reader = new StrmManifestReader();
        var repository = new InMemoryStrmFingerprintRepository();
        var item = CreateItem(fixture.Path, oldUrl);
        var key = SourceKey(item.Id);
        repository.TryCommit(Fingerprint(item.Id, reader.Read(fixture.Path).Manifest!), expectedPrevious: null);
        fixture.Write(newUrl, ValidSha1, 42);

        using var coordinator = new ProbeCoordinator(1);
        var native = ScriptedManager.Create();
        var captured = Source(oldUrl);
        captured.Id = key;
        native.StaticSources = [captured];
        native.Playback = (_, _, _, _) => throw new IOException("controlled native delegation failure");
        var settings = new MutablePlaybackSettings();
        var optimizer = CreateOptimizer(repository, settings: settings, coordinator: coordinator);

        var blocker = await coordinator.AcquireAsync(Guid.NewGuid(), "unrelated-source", "unrelated", CancellationToken.None);
        var queued = optimizer.CheckSourceAsync(native.Interface, item.Id, item, captured, key, true, null, false, CancellationToken.None, isPlaybackContext: true);
        Assert.IsFalse(queued.IsCompleted);

        // The queued owner re-reads Enabled=false and then delegates; the native delegation throws. The original
        // exception must propagate, but the permit and preparing registration must not leak.
        settings.Enabled = false;
        coordinator.Abandon(blocker.Item);

        await AssertThrowsAsync<IOException>(() => queued);
        Assert.AreEqual(0, coordinator.ActivePermits, "An admission delegation failure must release the global permit.");
        Assert.AreEqual(0, coordinator.PreparingCount, "An admission delegation failure must clear the preparing registration.");
        Assert.AreEqual(0, coordinator.RunningCount);

        // The pool is usable again: a later, unrelated source can acquire the only permit.
        var recovered = await coordinator.AcquireAsync(Guid.NewGuid(), "recovered-source", "h", CancellationToken.None)
            .WaitAsync(TimeSpan.FromSeconds(10));
        Assert.IsTrue(recovered.IsOwner);
        coordinator.Abandon(recovered.Item);
        Assert.AreEqual(0, coordinator.ActivePermits);
    }

    [TestMethod]
    public async Task OwnerImmediatelyAcquiringAPermitReReadsAVersionAcceptedBeforeItActs()
    {
        const string oldUrl = "https://media.example.invalid/video.mp4?sig=old";
        const string newUrl = "https://media.example.invalid/video.mp4?sig=new";
        using var fixture = new ManifestFixture(oldUrl, ValidSha1, 42);
        var reader = new StrmManifestReader();
        var repository = new InMemoryStrmFingerprintRepository();
        var item = CreateItem(fixture.Path, oldUrl);
        var key = SourceKey(item.Id);
        repository.TryCommit(Fingerprint(item.Id, reader.Read(fixture.Path).Manifest!), expectedPrevious: null);
        fixture.Write(newUrl, ValidSha1, 42);

        using var coordinator = new ProbeCoordinator(2);
        var native = ScriptedManager.Create();
        var streamRepository = ProbePersistenceDispatchProxy.Create(NativePersistence.Create<IMediaStreamRepository>());
        var itemPersistence = ProbePersistenceDispatchProxy.Create(NativePersistence.Create<IItemPersistenceService>());
        var probeExecutions = 0;
        var captured = Source(oldUrl);
        captured.Id = key;
        native.StaticSources = [captured];
        var preparing = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var releaseFirst = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        native.Playback = async (updatedItem, allowProbe, _, _) =>
        {
            Assert.IsTrue(allowProbe);
            preparing.TrySetResult();
            await releaseFirst.Task;
            Interlocked.Increment(ref probeExecutions);
            var result = MediaInfoWithVideo();
            ProbeExecutionContext.Current!.MarkCall(newUrl);
            ProbeExecutionContext.Current.RecordResult(newUrl, result);
            streamRepository.SaveMediaStreams(updatedItem.Id, result.MediaStreams, CancellationToken.None);
            updatedItem.ShortcutPath = newUrl;
            itemPersistence.SaveItems([updatedItem], CancellationToken.None);
            native.StaticSources = [Source(newUrl)];
            return [Source(newUrl)];
        };
        var optimizer = CreateOptimizer(repository, coordinator: coordinator);

        // The first owner is only preparing. The second request acquires the spare permit immediately, but the
        // first owner starts, saves, commits and settles while the second is paused before registration. The
        // second must re-read the now-accepted version instead of running a duplicate probe.
        var first = optimizer.CheckSourceAsync(native.Interface, item.Id, item, captured, key, true, null, false, CancellationToken.None, isPlaybackContext: true);
        await preparing.Task.WaitAsync(TimeSpan.FromSeconds(10));
        var barrierReached = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        coordinator.PermitAcquiredBarrier = () =>
        {
            barrierReached.TrySetResult();
            releaseFirst.TrySetResult();
            first.Wait(TimeSpan.FromSeconds(10));
        };
        var second = optimizer.CheckSourceAsync(native.Interface, item.Id, item, captured, key, true, null, false, CancellationToken.None, isPlaybackContext: true);
        await barrierReached.Task.WaitAsync(TimeSpan.FromSeconds(10));
        await first;
        var secondResult = await second.WaitAsync(TimeSpan.FromSeconds(10));

        Assert.AreEqual(1, probeExecutions, "A completed same-source execution must be reused, not probed again.");
        Assert.IsNull(secondResult, "The second owner reuses the accepted version instead of returning a fresh replacement.");
        Assert.AreEqual(0, coordinator.RunningCount);
        Assert.AreEqual(0, coordinator.PreparingCount);
        Assert.AreEqual(0, coordinator.ActivePermits);
    }

    [TestMethod]
    public async Task QueuedFirstTrustIsNotPublishedWhenTheManifestChangesDuringTheCurrentSourceRead()
    {
        const string firstUrl = "https://media.example.invalid/trust-a.mp4";
        const string laterUrl = "https://media.example.invalid/trust-b.mp4";
        using var fixture = new ManifestFixture(firstUrl, ValidSha1, 42);
        var reader = new StrmManifestReader();
        var repository = new InMemoryStrmFingerprintRepository();
        var item = CreateItem(fixture.Path, firstUrl);
        var key = SourceKey(item.Id);
        var firstHash = reader.Read(fixture.Path).Manifest!.UrlHash;

        using var coordinator = new ProbeCoordinator(1);
        var native = ScriptedManager.Create();
        // The queued request starts with no primary stream, so it must re-read the current native source.
        var captured = Source(firstUrl);
        captured.Id = key;
        captured.MediaStreams = [];
        native.StaticSources = [captured];
        var optimizer = CreateOptimizer(repository, coordinator: coordinator);

        var blocker = await coordinator.AcquireAsync(Guid.NewGuid(), "unrelated-source", "unrelated", CancellationToken.None);
        var queued = optimizer.CheckSourceAsync(native.Interface, item.Id, item, captured, key, true, null, false, CancellationToken.None, isPlaybackContext: true);
        Assert.IsFalse(queued.IsCompleted, "The request must be waiting for a permit.");

        // While queued, the native source gains a primary stream (so the decision becomes first trust) but the
        // STRM changes to another version during the admission's no-probe current-source read.
        native.StaticSources = [Source(firstUrl)];
        native.OnNativeNoProbe = _ => fixture.Write(laterUrl, ValidSha1, 42);
        coordinator.Abandon(blocker.Item);

        try
        {
            await queued.WaitAsync(TimeSpan.FromSeconds(10));
        }
        catch (InvalidOperationException)
        {
            // A manifest that changed during admission requires a caller retry; the key point is that no stale
            // first-trust fingerprint was published.
        }

        Assert.IsNull(repository.Get(item.Id, key), "A first trust must not be published for a STRM version that changed during admission.");
        Assert.AreNotEqual(firstHash, reader.Read(fixture.Path).Manifest!.UrlHash, "The fixture must have changed during the read for this regression to be meaningful.");
        Assert.AreEqual(0, coordinator.RunningCount);
        Assert.AreEqual(0, coordinator.PreparingCount);
        Assert.AreEqual(0, coordinator.ActivePermits);
    }

    [TestMethod]
    public async Task SharedProbeCallersReceiveTheirOwnDistinctResponses()
    {
        const string oldUrl = "https://media.example.invalid/video.mp4?sig=old";
        const string newUrl = "https://media.example.invalid/video.mp4?sig=new";
        using var fixture = new ManifestFixture(oldUrl, ValidSha1, 42);
        var reader = new StrmManifestReader();
        var repository = new InMemoryStrmFingerprintRepository();
        var item = CreateItem(fixture.Path, oldUrl);
        repository.TryCommit(Fingerprint(item.Id, reader.Read(fixture.Path).Manifest!), expectedPrevious: null);
        fixture.Write(newUrl, ValidSha1, 42);

        using var coordinator = new ProbeCoordinator(2);
        var native = ScriptedManager.Create();
        var streamRepository = ProbePersistenceDispatchProxy.Create(NativePersistence.Create<IMediaStreamRepository>());
        var itemPersistence = ProbePersistenceDispatchProxy.Create(NativePersistence.Create<IItemPersistenceService>());
        var probeStarted = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var releaseProbe = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var alice = new User("alice", "provider", "provider");
        var bob = new User("bob", "provider", "provider");

        // Each caller sees a source labelled for that user. A shared probe must not hand one caller another's source.
        static MediaSourceInfo NamedSource(Guid id, string url, string name)
        {
            return new MediaSourceInfo { Id = id.ToString("N"), Path = url, Name = name, MediaStreams = [new MediaStream { Type = MediaStreamType.Video }] };
        }

        native.StaticSourceResolver = (_, user) => [NamedSource(item.Id, newUrl, user?.Username ?? "anonymous")];
        native.Playback = async (updatedItem, _, _, _) =>
        {
            ProbeExecutionContext.Current!.MarkCall(newUrl);
            probeStarted.TrySetResult();
            await releaseProbe.Task;
            var result = MediaInfoWithVideo();
            ProbeExecutionContext.Current.RecordResult(newUrl, result);
            streamRepository.SaveMediaStreams(updatedItem.Id, result.MediaStreams, CancellationToken.None);
            updatedItem.ShortcutPath = newUrl;
            itemPersistence.SaveItems([updatedItem], CancellationToken.None);
            return [NamedSource(item.Id, newUrl, "alice-probe")];
        };
        var optimizer = CreateOptimizer(repository, coordinator: coordinator);

        var leader = optimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, alice, true, false, CancellationToken.None);
        await probeStarted.Task;
        var follower = optimizer.GetPlaybackMediaSourcesAsync(native.Interface, item, bob, true, false, CancellationToken.None);
        releaseProbe.TrySetResult();
        var results = await Task.WhenAll(leader, follower);

        Assert.AreEqual("alice-probe", results[0][0].Name, "The leading caller must receive its own probed source.");
        Assert.AreEqual("bob", results[1][0].Name, "The joining caller must re-read its own user-visible source, not the leader's.");
        Assert.AreEqual(0, coordinator.RunningCount);
        Assert.AreEqual(0, coordinator.ActivePermits);
    }

    private static StrmPlaybackOptimizer CreateOptimizer(
        IStrmFingerprintRepository repository,
        ILibraryManager? libraryManager = null,
        IPlaybackSettings? settings = null,
        ProbeCoordinator? coordinator = null)
    {
        return new StrmPlaybackOptimizer(
            new StrmManifestReader(),
            new ProbeDecisionService(),
            repository,
            settings ?? new PlaybackSettings(true),
            NullLogger<StrmPlaybackOptimizer>.Instance,
            libraryManager,
            coordinator);
    }

    private static Video CreateItem(string path, string url)
    {
        return new Video { Id = Guid.NewGuid(), Path = path, ShortcutPath = url };
    }

    private static MediaSourceInfo Source(string url, MediaStream? videoStream = null)
    {
        return new MediaSourceInfo
        {
            Path = url,
            MediaStreams = [videoStream ?? new MediaStream { Type = MediaStreamType.Video }]
        };
    }

    private static MediaSourceInfo SourceFor(Guid sourceId, string url, MediaStream? videoStream = null)
    {
        return new MediaSourceInfo
        {
            Id = sourceId.ToString("N"),
            Path = url,
            MediaStreams = [videoStream ?? new MediaStream { Type = MediaStreamType.Video }]
        };
    }

    private static MediaInfo MediaInfoWithVideo(string? codec = null, int? width = null, int? height = null)
    {
        return new MediaInfo
        {
            MediaStreams = [new MediaStream { Type = MediaStreamType.Video, Codec = codec, Width = width, Height = height }]
        };
    }

    private static StrmFingerprint Fingerprint(Guid itemId, StrmManifest manifest)
    {
        return new StrmFingerprint(itemId, SourceKey(itemId), manifest.UrlHash, manifest.Sha1, manifest.Size);
    }

    private static StrmFingerprint Fingerprint(Guid projectId, Guid sourceId, StrmManifest manifest)
    {
        return new StrmFingerprint(projectId, SourceKey(sourceId), manifest.UrlHash, manifest.Sha1, manifest.Size);
    }

    private static ProbeDecisionKind DecisionKind(StrmManifest manifest, StrmFingerprint? previous)
    {
        return new ProbeDecisionService().Decide(manifest, previous, hasPrimaryStream: true, nativeUrl: manifest.Url).Kind;
    }

    private static string SourceKey(Guid sourceId)
    {
        return sourceId.ToString("N");
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

    private static TException AssertThrows<TException>(Action action)
        where TException : Exception
    {
        try
        {
            action();
        }
        catch (TException exception)
        {
            return exception;
        }

        throw new AssertFailedException($"Expected {typeof(TException).Name}.");
    }

    private sealed record PlaybackSettings(
        bool PlaybackAutoCheck,
        bool Enabled = true,
        bool DetailedLog = false,
        int MaxConcurrentProbes = PluginConfiguration.DefaultMaxConcurrentProbes) : IPlaybackSettings;

    private sealed class MutablePlaybackSettings : IPlaybackSettings
    {
        public bool Enabled { get; set; } = true;

        public bool PlaybackAutoCheck { get; set; } = true;

        public bool DetailedLog { get; set; }

        public int MaxConcurrentProbes { get; set; } = PluginConfiguration.DefaultMaxConcurrentProbes;
    }

    private sealed class FaultInjectingFingerprintRepository : IStrmFingerprintRepository
    {
        private readonly InMemoryStrmFingerprintRepository _inner = new();

        public int GetCalls { get; private set; }

        public int CommitCalls { get; private set; }

        public StrmFingerprint? Get(Guid itemId, string sourceKey)
        {
            GetCalls++;
            throw new IOException("Injected fingerprint store read failure.");
        }

        public bool TryCommit(StrmFingerprint candidate, StrmFingerprint? expectedPrevious)
        {
            CommitCalls++;
            return _inner.TryCommit(candidate, expectedPrevious);
        }
    }

    public class NativePersistence : DispatchProxy
    {
        private string? _failureMethodName;

        public static T Create<T>()
            where T : class
        {
            return Create<T>(null);
        }

        public static T Create<T>(string? failureMethodName)
            where T : class
        {
            var proxy = DispatchProxy.Create<T, NativePersistence>();
            ((NativePersistence)(object)proxy)._failureMethodName = failureMethodName;
            return proxy;
        }

        protected override object? Invoke(MethodInfo? targetMethod, object?[]? args)
        {
            if (targetMethod is null)
            {
                throw new InvalidOperationException("Missing persistence method.");
            }

            if (string.Equals(targetMethod.Name, _failureMethodName, StringComparison.Ordinal))
            {
                throw new InvalidOperationException("Injected native persistence failure.");
            }

            if (targetMethod.ReturnType == typeof(void))
            {
                return null;
            }

            if (targetMethod.ReturnType == typeof(Task))
            {
                return Task.CompletedTask;
            }

            if (targetMethod.ReturnType.IsGenericType && targetMethod.ReturnType.GetGenericTypeDefinition() == typeof(Task<>))
            {
                var resultType = targetMethod.ReturnType.GenericTypeArguments[0];
                var value = resultType.IsValueType ? Activator.CreateInstance(resultType) : null;
                return typeof(Task).GetMethod(nameof(Task.FromResult))!.MakeGenericMethod(resultType).Invoke(null, [value]);
            }

            return targetMethod.ReturnType.IsValueType ? Activator.CreateInstance(targetMethod.ReturnType) : null;
        }
    }

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

        public List<bool> NoProbePathSubstitutions { get; } = [];

        public Action<BaseItem>? OnNativeNoProbe { get; set; }

        public IReadOnlyList<MediaSourceInfo> StaticSources { get; set; } = [];

        /// <summary>
        /// Gets or sets an optional resolver that produces the visible sources for the requesting user. It lets a
        /// regression prove that a shared probe still re-reads each caller's own native source instead of reusing
        /// the leading caller's response.
        /// </summary>
        public Func<BaseItem, User?, IReadOnlyList<MediaSourceInfo>>? StaticSourceResolver { get; set; }

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
                var staticItem = (BaseItem)args![0]!;
                var staticUser = args[1] as User;
                return EnsureSingleSourceId(staticItem, StaticSourceResolver?.Invoke(staticItem, staticUser) ?? StaticSources);
            }

            if (targetMethod.Name == nameof(IMediaSourceManager.GetPlaybackMediaSources) && args is { Length: 5 })
            {
                PlaybackCalls++;
                var item = (BaseItem)args[0]!;
                var allowProbe = (bool)args[2]!;
                LastAllowMediaProbe |= allowProbe;
                if (allowProbe)
                {
                    var task = _playback?.Invoke(item, allowProbe, (bool)args[3]!, (CancellationToken)args[4]!)
                        ?? Task.FromResult(StaticSourceResolver?.Invoke(item, args[1] as User) ?? StaticSources);
                    return EnsureSingleSourceIdAsync(item, task);
                }

                OnNativeNoProbe?.Invoke(item);
                NoProbePathSubstitutions.Add((bool)args[3]!);
                var noProbeTask = Task.FromResult(StaticSourceResolver?.Invoke(item, args[1] as User) ?? StaticSources);
                return EnsureSingleSourceIdAsync(item, noProbeTask);
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

        private static IReadOnlyList<MediaSourceInfo> EnsureSingleSourceId(BaseItem item, IReadOnlyList<MediaSourceInfo> sources)
        {
            if (sources.Count == 1 && string.IsNullOrEmpty(sources[0].Id))
            {
                sources[0].Id = item.Id.ToString("N");
            }

            return sources;
        }

        private static async Task<IReadOnlyList<MediaSourceInfo>> EnsureSingleSourceIdAsync(
            BaseItem item,
            Task<IReadOnlyList<MediaSourceInfo>> sourcesTask)
        {
            var sources = await sourcesTask.ConfigureAwait(false);
            return EnsureSingleSourceId(item, sources);
        }
    }

    public class ItemLookup : DispatchProxy
    {
        private IReadOnlyDictionary<Guid, BaseItem> _items = new Dictionary<Guid, BaseItem>();

        public ILibraryManager Interface { get; private set; } = null!;

        public static ItemLookup Create(params BaseItem[] items)
        {
            var proxy = DispatchProxy.Create<ILibraryManager, ItemLookup>();
            var lookup = (ItemLookup)(object)proxy;
            lookup.Interface = proxy;
            lookup._items = items.ToDictionary(item => item.Id);
            return lookup;
        }

        protected override object? Invoke(MethodInfo? targetMethod, object?[]? args)
        {
            if (targetMethod?.Name.StartsWith(nameof(ILibraryManager.GetItemById), StringComparison.Ordinal) == true
                && args is { Length: > 0 }
                && args[0] is Guid itemId
                && _items.TryGetValue(itemId, out var item))
            {
                return item;
            }

            return targetMethod?.ReturnType == typeof(void)
                ? null
                : targetMethod?.ReturnType.IsValueType == true
                    ? Activator.CreateInstance(targetMethod.ReturnType)
                    : null;
        }
    }
}
