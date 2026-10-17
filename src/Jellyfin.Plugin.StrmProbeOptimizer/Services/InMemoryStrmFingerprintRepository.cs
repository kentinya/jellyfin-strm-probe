using System.Collections.Concurrent;

namespace Jellyfin.Plugin.StrmProbeOptimizer.Services;

public interface IStrmFingerprintRepository
{
    StrmFingerprint? Get(Guid itemId, string sourceKey);

    bool TryCommit(StrmFingerprint candidate, StrmFingerprint? expectedPrevious);
}

public sealed class InMemoryStrmFingerprintRepository : IStrmFingerprintRepository
{
    private readonly ConcurrentDictionary<(Guid ItemId, string SourceKey), StrmFingerprint> _fingerprints = new();
    private readonly ConcurrentDictionary<(Guid ItemId, string SourceKey), object> _locks = new();

    public StrmFingerprint? Get(Guid itemId, string sourceKey)
    {
        return _fingerprints.TryGetValue((itemId, sourceKey), out var fingerprint) ? fingerprint : null;
    }

    public bool TryCommit(StrmFingerprint candidate, StrmFingerprint? expectedPrevious)
    {
        var key = (candidate.ItemId, candidate.SourceKey);
        var sync = _locks.GetOrAdd(key, static _ => new object());

        lock (sync)
        {
            _fingerprints.TryGetValue(key, out var current);
            if (!Equals(current, expectedPrevious))
            {
                return false;
            }

            _fingerprints[key] = candidate;
            return true;
        }
    }
}
