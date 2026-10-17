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
    public void HistoricalUrlChangeRequiresProbeWhenNativeAddressAlreadyMatchesCurrentManifest()
    {
        var previous = Fingerprint(CurrentUrl, ValidSha1, 24);
        var currentUrl = "https://media.example.invalid/video.mp4?sig=b";
        var manifest = Manifest(currentUrl, ValidSha1, 24);

        var decision = _service.Decide(manifest, previous, hasPrimaryStream: true, nativeUrl: currentUrl);

        Assert.AreEqual(ProbeDecisionKind.RequireProbe, decision.Kind);
        Assert.AreEqual(ProbeDecisionReason.UrlChanged, decision.Reason);
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
    public void InvalidHistoricalSizesAreNotComparedAsValidValues()
    {
        var negativePrevious = Fingerprint(CurrentUrl, sha1: null, size: -1);
        var negativeCurrent = Manifest(CurrentUrl, sha1: null, size: -2);
        var zeroPrevious = Fingerprint(CurrentUrl, sha1: null, size: 0);

        Assert.AreEqual(ProbeDecisionReason.InsufficientFingerprint, _service.Decide(negativeCurrent, negativePrevious, true, CurrentUrl).Reason);
        Assert.AreEqual(ProbeDecisionReason.InsufficientFingerprint, _service.Decide(Manifest(CurrentUrl, null, 0), negativePrevious, true, CurrentUrl).Reason);
        Assert.AreEqual(ProbeDecisionKind.RequireProbe, _service.Decide(Manifest(CurrentUrl, null, 1), zeroPrevious, true, CurrentUrl).Kind);
        Assert.AreEqual(ProbeDecisionKind.SkipProbe, _service.Decide(Manifest(CurrentUrl, null, 0), zeroPrevious, true, CurrentUrl).Kind);
    }

    [TestMethod]
    public void SizeIsUsedWhenOnlyOneSideHasAValidSha1()
    {
        var previous = Fingerprint(CurrentUrl, sha1: "invalid", size: 24);

        Assert.AreEqual(ProbeDecisionKind.RequireProbe, _service.Decide(Manifest(CurrentUrl, ValidSha1, 25), previous, true, CurrentUrl).Kind);
        Assert.AreEqual(ProbeDecisionKind.SkipProbe, _service.Decide(Manifest(CurrentUrl, ValidSha1, 24), previous, true, CurrentUrl).Kind);
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

    [TestMethod]
    public void ChangedUrlProbesForEveryHashAndSizeCombinationWhenNativeAddressMatchesTheManifest()
    {
        const string historicalUrl = "https://media.example.invalid/video.mp4?sig=historical";
        const string currentUrl = "https://media.example.invalid/video.mp4?sig=current";
        const string otherSha1 = "fedcba9876543210fedcba9876543210fedcba98";

        // The native address already equals the current manifest; only the stored historical URL differs.
        var cases = new[]
        {
            (previous: Fingerprint(historicalUrl, ValidSha1, 24), manifest: Manifest(currentUrl, otherSha1, 24), label: "both SHA-1 valid and different"),
            (previous: Fingerprint(historicalUrl, ValidSha1, 24), manifest: Manifest(currentUrl, null, 24), label: "previous SHA-1 valid only, Size equal"),
            (previous: Fingerprint(historicalUrl, null, 24), manifest: Manifest(currentUrl, ValidSha1, 24), label: "current SHA-1 valid only, Size equal"),
            (previous: Fingerprint(historicalUrl, null, 24), manifest: Manifest(currentUrl, null, 24), label: "both SHA-1 missing, Size equal"),
            (previous: Fingerprint(historicalUrl, null, 24), manifest: Manifest(currentUrl, null, 99), label: "both SHA-1 missing, Size different"),
            (previous: Fingerprint(historicalUrl, null, null), manifest: Manifest(currentUrl, null, null), label: "both SHA-1 and Size missing"),
            (previous: Fingerprint(historicalUrl, "invalid", 24), manifest: Manifest(currentUrl, null, 99), label: "both SHA-1 invalid, Size different"),
            (previous: Fingerprint(historicalUrl, ValidSha1, null), manifest: Manifest(currentUrl, null, null), label: "previous SHA-1 valid only, Size missing"),
        };

        foreach (var (previous, manifest, label) in cases)
        {
            var decision = _service.Decide(manifest, previous, hasPrimaryStream: true, nativeUrl: currentUrl);
            Assert.AreEqual(ProbeDecisionKind.RequireProbe, decision.Kind, label);
            Assert.AreEqual(ProbeDecisionReason.UrlChanged, decision.Reason, label);
        }
    }

    [TestMethod]
    public void NativeAddressMismatchOutranksStoredUrlAndHashComparison()
    {
        var changedManifest = Manifest("https://media.example.invalid/video.mp4?sig=changed", ValidSha1, 24);
        var previous = Fingerprint(CurrentUrl, ValidSha1, 24);

        var decision = _service.Decide(changedManifest, previous, hasPrimaryStream: true, nativeUrl: CurrentUrl);

        Assert.AreEqual(ProbeDecisionKind.RequireProbe, decision.Kind);
        Assert.AreEqual(ProbeDecisionReason.NativeUrlMismatch, decision.Reason);
    }

    [TestMethod]
    public void SameUrlShaValidityCombinationsCoverBothDirectionsAndSizeComparability()
    {
        // Both sides valid: the SHA-1 decides and a matching SHA-1 ignores Size.
        AssertSkip(SameUrlDecision(ValidSha1, 24, ValidSha1, 99), ProbeDecisionReason.Sha1Matches, "both valid, equal SHA-1 ignores Size");
        AssertRequire(SameUrlDecision(ValidSha1, 24, new string('f', 40), 24), ProbeDecisionReason.Sha1Changed, "both valid, different SHA-1");

        // Every direction where at least one side lacks a valid SHA-1: only different valid Sizes require a probe.
        var shaPairs = new (string? Previous, string? Current, string Label)[]
        {
            (ValidSha1, null, "previous valid, current missing"),
            (ValidSha1, "invalid", "previous valid, current invalid"),
            (null, ValidSha1, "previous missing, current valid"),
            ("invalid", ValidSha1, "previous invalid, current valid"),
            (null, null, "both missing"),
            (null, "invalid", "previous missing, current invalid"),
            ("invalid", null, "previous invalid, current missing"),
            ("invalid", "invalid", "both invalid"),
        };

        foreach (var (previousSha, currentSha, label) in shaPairs)
        {
            AssertRequire(SameUrlDecision(previousSha, 24, currentSha, 25), ProbeDecisionReason.SizeChanged, label + ", Size different");
            AssertSkip(SameUrlDecision(previousSha, 24, currentSha, 24), ProbeDecisionReason.Unchanged, label + ", Size equal");
            AssertSkip(SameUrlDecision(previousSha, null, currentSha, null), ProbeDecisionReason.InsufficientFingerprint, label + ", Size missing on both sides");
            AssertSkip(SameUrlDecision(previousSha, 24, currentSha, null), ProbeDecisionReason.InsufficientFingerprint, label + ", current Size missing");
            AssertSkip(SameUrlDecision(previousSha, null, currentSha, 24), ProbeDecisionReason.InsufficientFingerprint, label + ", previous Size missing");
        }
    }

    private ProbeDecision SameUrlDecision(string? previousSha1, long? previousSize, string? currentSha1, long? currentSize)
    {
        return _service.Decide(Manifest(CurrentUrl, currentSha1, currentSize), Fingerprint(CurrentUrl, previousSha1, previousSize), hasPrimaryStream: true, nativeUrl: CurrentUrl);
    }

    private static void AssertSkip(ProbeDecision decision, ProbeDecisionReason reason, string label)
    {
        Assert.AreEqual(ProbeDecisionKind.SkipProbe, decision.Kind, label);
        Assert.AreEqual(reason, decision.Reason, label);
    }

    private static void AssertRequire(ProbeDecision decision, ProbeDecisionReason reason, string label)
    {
        Assert.AreEqual(ProbeDecisionKind.RequireProbe, decision.Kind, label);
        Assert.AreEqual(reason, decision.Reason, label);
    }

    [TestMethod]
    public void ShaValidityCombinationsFollowTheDocumentedMatrix()
    {
        var previousValid = Fingerprint(CurrentUrl, ValidSha1, 24);
        var previousMissing = Fingerprint(CurrentUrl, sha1: null, size: 24);
        var previousInvalid = Fingerprint(CurrentUrl, sha1: "invalid", size: 24);

        // Both sides valid: the SHA-1 decides and a matching SHA-1 ignores Size.
        Assert.AreEqual(ProbeDecisionKind.SkipProbe, _service.Decide(Manifest(CurrentUrl, ValidSha1, 99), previousValid, true, CurrentUrl).Kind);
        Assert.AreEqual(ProbeDecisionKind.RequireProbe, _service.Decide(Manifest(CurrentUrl, new string('f', 40), 24), previousValid, true, CurrentUrl).Kind);

        // One or both sides without a valid SHA-1: only different valid Sizes require a probe.
        foreach (var previous in new[] { previousMissing, previousInvalid })
        {
            Assert.AreEqual(ProbeDecisionReason.SizeChanged, _service.Decide(Manifest(CurrentUrl, ValidSha1, 25), previous, true, CurrentUrl).Reason);
            Assert.AreEqual(ProbeDecisionKind.SkipProbe, _service.Decide(Manifest(CurrentUrl, ValidSha1, 24), previous, true, CurrentUrl).Kind);
            Assert.AreEqual(ProbeDecisionKind.SkipProbe, _service.Decide(Manifest(CurrentUrl, null, 24), previous, true, CurrentUrl).Kind);
            Assert.AreEqual(ProbeDecisionReason.InsufficientFingerprint, _service.Decide(Manifest(CurrentUrl, null, null), previous, true, CurrentUrl).Reason);
        }

        // Zero is a valid Size and must be compared like any other valid value.
        Assert.AreEqual(ProbeDecisionKind.RequireProbe, _service.Decide(Manifest(CurrentUrl, null, 0), Fingerprint(CurrentUrl, null, 24), true, CurrentUrl).Kind);
        Assert.AreEqual(ProbeDecisionKind.SkipProbe, _service.Decide(Manifest(CurrentUrl, null, 0), Fingerprint(CurrentUrl, null, 0), true, CurrentUrl).Kind);
    }

    [TestMethod]
    public void MissingPrimaryStreamOutranksUrlChangeAndFingerprint()
    {
        var previous = Fingerprint(CurrentUrl, ValidSha1, 24);
        var changed = Manifest("https://media.example.invalid/video.mp4?sig=changed", ValidSha1, 24);

        var decision = _service.Decide(changed, previous, hasPrimaryStream: false, nativeUrl: CurrentUrl);

        Assert.AreEqual(ProbeDecisionKind.RequireProbe, decision.Kind);
        Assert.AreEqual(ProbeDecisionReason.MissingPrimaryStream, decision.Reason);
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
