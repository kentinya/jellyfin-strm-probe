using System.Security.Cryptography;
using System.Text;
using Jellyfin.Plugin.StrmProbeOptimizer.Services;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace Jellyfin.Plugin.StrmProbeOptimizer.Tests;

[TestClass]
public sealed class ProbeDecisionServiceTests
{
    private const string ValidSha1 = "0123456789abcdef0123456789abcdef01234567";
    private const string CurrentUrl = "https://media.example.invalid/video.mp4?sig=a";
    private readonly ProbeDecisionService _service = new();

    [TestMethod]
    public void UrlChangeRequiresProbeEvenWhenShaAndSizeMatch()
    {
        var previous = Fingerprint(CurrentUrl, ValidSha1, 24);
        var manifest = Manifest("https://media.example.invalid/video.mp4?sig=b", ValidSha1, 24);

        var decision = _service.Decide(manifest, previous, hasPrimaryStream: true, nativeUrl: CurrentUrl);

        Assert.AreEqual(ProbeDecisionKind.RequireProbe, decision.Kind);
        Assert.AreEqual(ProbeDecisionReason.NativeUrlMismatch, decision.Reason);
    }

    [TestMethod]
    public void SameUrlAndShaSkipsRegardlessOfSizeDifference()
    {
        var previous = Fingerprint(CurrentUrl, ValidSha1, 24);
        var manifest = Manifest(CurrentUrl, ValidSha1.ToUpperInvariant(), 99);

        var decision = _service.Decide(manifest, previous, hasPrimaryStream: true, nativeUrl: CurrentUrl);

        Assert.AreEqual(ProbeDecisionKind.SkipProbe, decision.Kind);
        Assert.AreEqual(ProbeDecisionReason.Sha1Matches, decision.Reason);
    }

    [TestMethod]
    public void DifferentComparableShaRequiresProbe()
    {
        var previous = Fingerprint(CurrentUrl, ValidSha1, 24);
        var manifest = Manifest(CurrentUrl, new string('f', 40), 24);

        Assert.AreEqual(ProbeDecisionKind.RequireProbe, _service.Decide(manifest, previous, true, CurrentUrl).Kind);
    }

    [TestMethod]
    public void UncomparableHashesUseOnlyDifferentValidSizes()
    {
        var previous = Fingerprint(CurrentUrl, sha1: null, size: 24);

        Assert.AreEqual(ProbeDecisionKind.RequireProbe, _service.Decide(Manifest(CurrentUrl, null, 25), previous, true, CurrentUrl).Kind);
        Assert.AreEqual(ProbeDecisionKind.SkipProbe, _service.Decide(Manifest(CurrentUrl, null, 24), previous, true, CurrentUrl).Kind);
        Assert.AreEqual(ProbeDecisionKind.SkipProbe, _service.Decide(Manifest(CurrentUrl, null, null), previous, true, CurrentUrl).Kind);
    }

    [TestMethod]
    public void MissingPrimaryStreamTakesPrecedenceOverFirstTrust()
    {
        var decision = _service.Decide(Manifest(CurrentUrl, ValidSha1, 24), previous: null, hasPrimaryStream: false, nativeUrl: CurrentUrl);

        Assert.AreEqual(ProbeDecisionKind.RequireProbe, decision.Kind);
        Assert.AreEqual(ProbeDecisionReason.MissingPrimaryStream, decision.Reason);
    }

    [TestMethod]
    public void FirstTrustRequiresTheNativeAddressToMatchTheManifest()
    {
        var manifest = Manifest(CurrentUrl, ValidSha1, 24);

        Assert.AreEqual(ProbeDecisionKind.TrustExisting, _service.Decide(manifest, null, true, CurrentUrl).Kind);
        Assert.AreEqual(ProbeDecisionKind.RequireProbe, _service.Decide(manifest, null, true, "https://media.example.invalid/old.mp4").Kind);
    }

    private static StrmFingerprint Fingerprint(string url, string? sha1, long? size)
    {
        return new StrmFingerprint(Guid.NewGuid(), "primary", HashUrl(url), sha1, size);
    }

    private static StrmManifest Manifest(string url, string? sha1, long? size)
    {
        return new StrmManifest(url, HashUrl(url), sha1, size, "content");
    }

    private static string HashUrl(string url)
    {
        return Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(url))).ToLowerInvariant();
    }
}
