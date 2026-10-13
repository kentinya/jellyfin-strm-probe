using System.Security.Cryptography;
using System.Text;
using Jellyfin.Plugin.StrmProbeOptimizer.Services;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace Jellyfin.Plugin.StrmProbeOptimizer.Tests;

[TestClass]
public sealed class ManifestReaderTests
{
    private readonly StrmManifestReader _reader = new();

    [TestMethod]
    public void ReadAcceptsVersionOneAndPreservesSignedUrl()
    {
        const string url = "https://media.example.invalid/watch?id=42&sig=private-value";
        var path = WriteFixture("\uFEFF# strm-probe-version:1\r\n# strm-probe-sha1:AABBCCDDEEFF0011223344556677889900112233\r\n# strm-probe-size:0\r\n" + url + "\r\n");

        try
        {
            var result = _reader.Read(path);

            Assert.AreEqual(ManifestReadStatus.Supported, result.Status);
            Assert.IsNotNull(result.Manifest);
            Assert.AreEqual(url, result.Manifest.Url);
            Assert.AreEqual("aabbccddeeff0011223344556677889900112233", result.Manifest.Sha1);
            Assert.AreEqual(0L, result.Manifest.Size);
            Assert.AreNotEqual(url, result.Manifest.UrlHash);
        }
        finally
        {
            File.Delete(path);
        }
    }

    [TestMethod]
    public void ContentHashIncludesBomBytesWhileParsingTheSameManifest()
    {
        const string contents = "# strm-probe-version:1\nhttps://media.example.invalid/video.mp4\n";
        var withBom = Path.Combine(Path.GetTempPath(), $"strm-probe-{Guid.NewGuid():N}.strm");
        var withoutBom = WriteFixture(contents);
        File.WriteAllText(withBom, contents, new UTF8Encoding(encoderShouldEmitUTF8Identifier: true));

        try
        {
            var bomResult = _reader.Read(withBom);
            var plainResult = _reader.Read(withoutBom);

            Assert.AreEqual(ManifestReadStatus.Supported, bomResult.Status);
            Assert.AreEqual(ManifestReadStatus.Supported, plainResult.Status);
            Assert.AreEqual(plainResult.Manifest?.Url, bomResult.Manifest?.Url);
            Assert.AreNotEqual(plainResult.Manifest?.ContentHash, bomResult.Manifest?.ContentHash);
        }
        finally
        {
            File.Delete(withBom);
            File.Delete(withoutBom);
        }
    }

    [TestMethod]
    public void ReadTreatsMissingProtocolAsUnsupported()
    {
        var path = WriteFixture("https://media.example.invalid/video.mp4\n");
        try
        {
            Assert.AreEqual(ManifestReadStatus.Unsupported, _reader.Read(path).Status);
        }
        finally
        {
            File.Delete(path);
        }
    }

    [TestMethod]
    public void ReadRejectsConflictingDuplicateMarkersAndRelativeUrls()
    {
        var conflicting = WriteFixture("# strm-probe-version:1\n# strm-probe-version:1\nhttps://media.example.invalid/video.mp4\n");
        var relative = WriteFixture("# strm-probe-version:1\nvideo.mp4\n");
        try
        {
            Assert.AreEqual(ManifestReadStatus.Invalid, _reader.Read(conflicting).Status);
            Assert.AreEqual(ManifestReadStatus.Invalid, _reader.Read(relative).Status);
        }
        finally
        {
            File.Delete(conflicting);
            File.Delete(relative);
        }
    }

    [TestMethod]
    public void ReadUsesJellyfinStrmLineNormalizationBeforeSelectingTheFirstAddress()
    {
        const string url = "https://media.example.invalid/video.mp4?token=one";
        var path = WriteFixture("# strm-probe-version:1\r\n\t" + url.Replace("media", "me\tdia", StringComparison.Ordinal) + "\r\nhttps://other.example.invalid/later.mp4\r\n");
        try
        {
            var result = _reader.Read(path);

            Assert.AreEqual(ManifestReadStatus.Supported, result.Status);
            Assert.AreEqual(url, result.Manifest?.Url);
        }
        finally
        {
            File.Delete(path);
        }
    }

    [TestMethod]
    public void ReadDoesNotSkipAnInvalidFirstAddressToFindALaterValidOne()
    {
        var path = WriteFixture("# strm-probe-version:1\nftp://media.example.invalid/first.mp4\nhttps://media.example.invalid/later.mp4\n");
        try
        {
            Assert.AreEqual(ManifestReadStatus.Invalid, _reader.Read(path).Status);
        }
        finally
        {
            File.Delete(path);
        }
    }

    [TestMethod]
    public void ReadRejectsInvalidUtf8AndDuplicateOptionalMarkers()
    {
        var invalidEncoding = Path.Combine(Path.GetTempPath(), $"strm-probe-{Guid.NewGuid():N}.strm");
        var duplicateMarker = WriteFixture("# strm-probe-version:1\n# strm-probe-size:0\n# strm-probe-size:1\nhttps://media.example.invalid/video.mp4\n");
        File.WriteAllBytes(invalidEncoding, [0x23, 0x20, 0xff]);
        try
        {
            Assert.AreEqual(ManifestReadStatus.Invalid, _reader.Read(invalidEncoding).Status);
            Assert.AreEqual(ManifestReadStatus.Invalid, _reader.Read(duplicateMarker).Status);
        }
        finally
        {
            File.Delete(invalidEncoding);
            File.Delete(duplicateMarker);
        }
    }

    [TestMethod]
    public void ReadTreatsMissingEmptyAndOverflowingSizesAsUnavailable()
    {
        var missing = WriteFixture("# strm-probe-version:1\nhttps://media.example.invalid/video.mp4\n");
        var empty = WriteFixture("# strm-probe-version:1\n# strm-probe-size:\nhttps://media.example.invalid/video.mp4\n");
        var overflow = WriteFixture("# strm-probe-version:1\n# strm-probe-size:9223372036854775808\nhttps://media.example.invalid/video.mp4\n");
        try
        {
            Assert.IsNull(_reader.Read(missing).Manifest?.Size);
            Assert.IsNull(_reader.Read(empty).Manifest?.Size);
            Assert.IsNull(_reader.Read(overflow).Manifest?.Size);
        }
        finally
        {
            File.Delete(missing);
            File.Delete(empty);
            File.Delete(overflow);
        }
    }

    [TestMethod]
    public void ReadMakesInvalidShaAndSizeUnavailableForComparison()
    {
        var path = WriteFixture("# strm-probe-version:1\n# strm-probe-sha1:not-a-hash\n# strm-probe-size:-1\nhttps://media.example.invalid/video.mp4\n");
        try
        {
            var result = _reader.Read(path);

            Assert.AreEqual(ManifestReadStatus.Supported, result.Status);
            Assert.IsNotNull(result.Manifest);
            Assert.IsNull(result.Manifest.Sha1);
            Assert.IsNull(result.Manifest.Size);
        }
        finally
        {
            File.Delete(path);
        }
    }

    [TestMethod]
    public void ReadRejectsFilesOverTheBoundedInputLimit()
    {
        var path = WriteFixture("# strm-probe-version:1\n" + new string('x', StrmManifestReader.MaxBytes));
        try
        {
            Assert.AreEqual(ManifestReadStatus.Invalid, _reader.Read(path).Status);
        }
        finally
        {
            File.Delete(path);
        }
    }

    private static string WriteFixture(string content)
    {
        var path = Path.Combine(Path.GetTempPath(), $"strm-probe-{Guid.NewGuid():N}.strm");
        File.WriteAllText(path, content, new UTF8Encoding(encoderShouldEmitUTF8Identifier: false));
        return path;
    }
}
