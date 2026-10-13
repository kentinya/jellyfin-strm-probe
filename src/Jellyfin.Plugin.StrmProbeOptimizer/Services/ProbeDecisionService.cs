namespace Jellyfin.Plugin.StrmProbeOptimizer.Services;

public enum ProbeDecisionKind
{
    RequireProbe,
    SkipProbe,
    TrustExisting
}

public enum ProbeDecisionReason
{
    MissingPrimaryStream,
    NativeUrlMismatch,
    FirstTrust,
    UrlChanged,
    Sha1Changed,
    Sha1Matches,
    SizeChanged,
    Unchanged,
    InsufficientFingerprint
}

public sealed record StrmFingerprint(Guid ItemId, string SourceKey, string UrlHash, string? Sha1, long? Size);

public sealed record ProbeDecision(ProbeDecisionKind Kind, ProbeDecisionReason Reason);

public interface IProbeDecisionService
{
    ProbeDecision Decide(StrmManifest manifest, StrmFingerprint? previous, bool hasPrimaryStream, string? nativeUrl);
}

public sealed class ProbeDecisionService : IProbeDecisionService
{
    public ProbeDecision Decide(StrmManifest manifest, StrmFingerprint? previous, bool hasPrimaryStream, string? nativeUrl)
    {
        if (!hasPrimaryStream)
        {
            return new ProbeDecision(ProbeDecisionKind.RequireProbe, ProbeDecisionReason.MissingPrimaryStream);
        }

        if (!string.Equals(nativeUrl, manifest.Url, StringComparison.Ordinal))
        {
            return new ProbeDecision(ProbeDecisionKind.RequireProbe, ProbeDecisionReason.NativeUrlMismatch);
        }

        if (previous is null)
        {
            return new ProbeDecision(ProbeDecisionKind.TrustExisting, ProbeDecisionReason.FirstTrust);
        }

        if (!string.Equals(previous.UrlHash, manifest.UrlHash, StringComparison.Ordinal))
        {
            return new ProbeDecision(ProbeDecisionKind.RequireProbe, ProbeDecisionReason.UrlChanged);
        }

        if (StrmManifestReader.IsValidSha1(previous.Sha1)
            && StrmManifestReader.IsValidSha1(manifest.Sha1))
        {
            return string.Equals(previous.Sha1, manifest.Sha1, StringComparison.OrdinalIgnoreCase)
                ? new ProbeDecision(ProbeDecisionKind.SkipProbe, ProbeDecisionReason.Sha1Matches)
                : new ProbeDecision(ProbeDecisionKind.RequireProbe, ProbeDecisionReason.Sha1Changed);
        }

        if (previous.Size.HasValue && manifest.Size.HasValue && previous.Size.Value != manifest.Size.Value)
        {
            return new ProbeDecision(ProbeDecisionKind.RequireProbe, ProbeDecisionReason.SizeChanged);
        }

        return new ProbeDecision(
            ProbeDecisionKind.SkipProbe,
            previous.Size.HasValue && manifest.Size.HasValue
                ? ProbeDecisionReason.Unchanged
                : ProbeDecisionReason.InsufficientFingerprint);
    }
}
