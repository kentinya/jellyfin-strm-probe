using System.Globalization;
using System.Security.Cryptography;
using System.Text;

namespace Jellyfin.Plugin.StrmProbeOptimizer.Services;

public enum ManifestReadStatus
{
    Supported,
    Unsupported,
    Invalid,
    Unavailable
}

public sealed record StrmManifest(
    string Url,
    string UrlHash,
    string? Sha1,
    long? Size,
    string ContentHash);

public sealed record ManifestReadResult(ManifestReadStatus Status, StrmManifest? Manifest)
{
    public static ManifestReadResult Unsupported { get; } = new(ManifestReadStatus.Unsupported, null);

    public static ManifestReadResult Invalid { get; } = new(ManifestReadStatus.Invalid, null);

    public static ManifestReadResult Unavailable { get; } = new(ManifestReadStatus.Unavailable, null);
}

public interface IStrmManifestReader
{
    ManifestReadResult Read(string path);
}

public sealed class StrmManifestReader : IStrmManifestReader
{
    public const int MaxBytes = 64 * 1024;
    private static readonly UTF8Encoding StrictUtf8 = new(false, true);

    public ManifestReadResult Read(string path)
    {
        try
        {
            using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
            if (stream.Length > MaxBytes)
            {
                return ManifestReadResult.Invalid;
            }

            var bytes = new byte[(int)stream.Length];
            var offset = 0;
            while (offset < bytes.Length)
            {
                var count = stream.Read(bytes, offset, bytes.Length - offset);
                if (count == 0)
                {
                    return ManifestReadResult.Invalid;
                }

                offset += count;
            }

            if (stream.ReadByte() != -1)
            {
                return ManifestReadResult.Invalid;
            }

            return Read(bytes);
        }
        catch (FileNotFoundException)
        {
            return ManifestReadResult.Unavailable;
        }
        catch (DirectoryNotFoundException)
        {
            return ManifestReadResult.Unavailable;
        }
        catch (UnauthorizedAccessException)
        {
            return ManifestReadResult.Unavailable;
        }
        catch (IOException)
        {
            return ManifestReadResult.Unavailable;
        }
    }

    internal static ManifestReadResult Read(ReadOnlySpan<byte> input)
    {
        if (input.Length > MaxBytes)
        {
            return ManifestReadResult.Invalid;
        }

        try
        {
            var contentHash = Convert.ToHexString(SHA256.HashData(input)).ToLowerInvariant();
            if (input.StartsWith(new byte[] { 0xEF, 0xBB, 0xBF }))
            {
                input = input[3..];
            }

            var contents = StrictUtf8.GetString(input);
            string? version = null;
            string? sha1Value = null;
            string? sizeValue = null;
            string? url = null;

            foreach (var rawLine in contents.Split('\n'))
            {
                var line = NormalizeStrmLine(rawLine);
                if (line.Length == 0)
                {
                    continue;
                }

                if (TryReadMarker(line, "# strm-probe-version:", ref version)
                    || TryReadMarker(line, "# strm-probe-sha1:", ref sha1Value)
                    || TryReadMarker(line, "# strm-probe-size:", ref sizeValue))
                {
                    continue;
                }

                if (line.StartsWith('#'))
                {
                    continue;
                }

                url ??= line;
            }

            if (version is null)
            {
                return ManifestReadResult.Unsupported;
            }

            if (!string.Equals(version, "1", StringComparison.Ordinal))
            {
                return ManifestReadResult.Unsupported;
            }

            if (url is null
                || !Uri.TryCreate(url, UriKind.Absolute, out var parsedUrl)
                || (parsedUrl.Scheme != Uri.UriSchemeHttp && parsedUrl.Scheme != Uri.UriSchemeHttps)
                || string.IsNullOrEmpty(parsedUrl.Host))
            {
                return ManifestReadResult.Invalid;
            }

            var normalizedSha1 = IsValidSha1(sha1Value) ? sha1Value!.ToLowerInvariant() : null;
            var parsedSize = long.TryParse(sizeValue, NumberStyles.None, CultureInfo.InvariantCulture, out var size)
                && size >= 0
                    ? size
                    : (long?)null;
            var urlHash = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(url))).ToLowerInvariant();

            return new ManifestReadResult(
                ManifestReadStatus.Supported,
                new StrmManifest(url, urlHash, normalizedSha1, parsedSize, contentHash));
        }
        catch (DecoderFallbackException)
        {
            return ManifestReadResult.Invalid;
        }
        catch (InvalidDataException)
        {
            return ManifestReadResult.Invalid;
        }
    }

    public static bool IsValidSha1(string? value)
    {
        if (value is null || value.Length != 40)
        {
            return false;
        }

        foreach (var character in value)
        {
            if (!Uri.IsHexDigit(character))
            {
                return false;
            }
        }

        return true;
    }

    public static bool IsValidSize(long? value)
    {
        return value is >= 0;
    }

    private static string NormalizeStrmLine(string line)
    {
        return line.Replace("\t", string.Empty, StringComparison.Ordinal)
            .Replace("\r", string.Empty, StringComparison.Ordinal)
            .Replace("\n", string.Empty, StringComparison.Ordinal)
            .Trim();
    }

    private static bool TryReadMarker(string line, string prefix, ref string? value)
    {
        if (!line.StartsWith(prefix, StringComparison.Ordinal))
        {
            return false;
        }

        if (value is not null)
        {
            throw new InvalidDataException("Duplicate STRM marker.");
        }

        value = line[prefix.Length..].Trim();
        return true;
    }
}
