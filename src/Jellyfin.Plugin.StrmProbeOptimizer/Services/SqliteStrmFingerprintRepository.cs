using System.Globalization;
using System.Reflection;
using System.Runtime.InteropServices;
using MediaBrowser.Common.Configuration;
using Microsoft.Data.Sqlite;

namespace Jellyfin.Plugin.StrmProbeOptimizer.Services;

public sealed class SqliteStrmFingerprintRepository : IStrmFingerprintRepository
{
    public const int CurrentSchemaVersion = 1;
    private const string TableName = "strm_fingerprint";
    private readonly string _databasePath;
    private readonly object _initializationLock = new();
    private int _initialized;

    static SqliteStrmFingerprintRepository()
    {
        SQLitePCL.Batteries.Init();
    }

    public SqliteStrmFingerprintRepository(IApplicationPaths applicationPaths)
        : this(GetDatabasePath(applicationPaths))
    {
    }

    public SqliteStrmFingerprintRepository(string databasePath)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(databasePath);
        _databasePath = Path.GetFullPath(databasePath);
    }

    public static string GetDatabasePath(IApplicationPaths applicationPaths)
    {
        ArgumentNullException.ThrowIfNull(applicationPaths);
        var pluginId = typeof(Plugin).Assembly.GetCustomAttribute<GuidAttribute>()?.Value
            ?? throw new InvalidOperationException("The plugin assembly has no stable identifier.");
        return Path.Combine(applicationPaths.DataPath, "plugins", Guid.Parse(pluginId).ToString("N", CultureInfo.InvariantCulture), "strm-fingerprints.db");
    }

    public StrmFingerprint? Get(Guid itemId, string sourceKey)
    {
        var normalizedSourceKey = NormalizeSourceKey(sourceKey);
        using var connection = OpenInitializedConnection();
        using var command = connection.CreateCommand();
        command.CommandText = "SELECT item_id, source_key, url_hash, sha1, file_size FROM strm_fingerprint WHERE item_id = $item_id AND source_key = $source_key;";
        command.Parameters.AddWithValue("$item_id", FormatId(itemId));
        command.Parameters.AddWithValue("$source_key", normalizedSourceKey);
        using var reader = command.ExecuteReader();
        return reader.Read() ? ReadFingerprint(reader, itemId, normalizedSourceKey) : null;
    }

    public bool TryCommit(StrmFingerprint candidate, StrmFingerprint? expectedPrevious)
    {
        ArgumentNullException.ThrowIfNull(candidate);
        candidate = NormalizeCandidate(candidate);
        if (expectedPrevious is not null)
        {
            expectedPrevious = NormalizeCandidate(expectedPrevious);
            if (expectedPrevious.ItemId != candidate.ItemId
                || !string.Equals(expectedPrevious.SourceKey, candidate.SourceKey, StringComparison.Ordinal))
            {
                throw new ArgumentException("The expected fingerprint must use the candidate project and source key.", nameof(expectedPrevious));
            }
        }

        using var connection = OpenInitializedConnection();
        using var transaction = connection.BeginTransaction(deferred: false);
        var current = GetWithinTransaction(connection, transaction, candidate.ItemId, candidate.SourceKey);
        if (!Equals(current, expectedPrevious))
        {
            return false;
        }

        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = """
            INSERT INTO strm_fingerprint(item_id, source_key, url_hash, sha1, file_size)
            VALUES ($item_id, $source_key, $url_hash, $sha1, $file_size)
            ON CONFLICT(item_id, source_key) DO UPDATE SET
                url_hash = excluded.url_hash,
                sha1 = excluded.sha1,
                file_size = excluded.file_size;
            """;
        AddFingerprintParameters(command, candidate);
        if (command.ExecuteNonQuery() != 1)
        {
            throw new InvalidOperationException("SQLite did not accept the fingerprint row.");
        }

        transaction.Commit();
        return true;
    }

    private SqliteConnection OpenInitializedConnection()
    {
        var directory = Path.GetDirectoryName(_databasePath);
        if (directory is not null)
        {
            Directory.CreateDirectory(directory);
        }

        var connection = new SqliteConnection(new SqliteConnectionStringBuilder
        {
            DataSource = _databasePath,
            Mode = SqliteOpenMode.ReadWriteCreate,
            Cache = SqliteCacheMode.Private,
            Pooling = false,
            DefaultTimeout = 30
        }.ToString());

        try
        {
            connection.Open();
            EnsureSchema(connection);
            return connection;
        }
        catch
        {
            connection.Dispose();
            throw;
        }
    }

    private void EnsureSchema(SqliteConnection connection)
    {
        if (Volatile.Read(ref _initialized) != 0)
        {
            return;
        }

        lock (_initializationLock)
        {
            if (_initialized != 0)
            {
                return;
            }

            using var transaction = connection.BeginTransaction(deferred: false);
            var version = ReadUserVersion(connection, transaction);
            if (version == 0)
            {
                var userObjectCount = ExecuteScalarInt64(
                    connection,
                    transaction,
                    "SELECT COUNT(*) FROM sqlite_master WHERE name NOT LIKE 'sqlite_%';");
                if (userObjectCount != 0)
                {
                    throw new InvalidDataException("The plugin database has an unversioned schema and was left unchanged.");
                }

                ExecuteNonQuery(connection, transaction, """
                    CREATE TABLE strm_fingerprint (
                        item_id TEXT NOT NULL,
                        source_key TEXT NOT NULL,
                        url_hash TEXT NOT NULL,
                        sha1 TEXT,
                        file_size INTEGER,
                        PRIMARY KEY (item_id, source_key)
                    );
                    """);
                ExecuteNonQuery(connection, transaction, $"PRAGMA user_version = {CurrentSchemaVersion};");
                transaction.Commit();
                ValidateSchema(connection, transaction: null);
                Volatile.Write(ref _initialized, 1);
                return;
            }

            if (version != CurrentSchemaVersion)
            {
                throw new InvalidDataException($"The plugin database schema version {version} is not supported.");
            }

            ValidateSchema(connection, transaction);
            transaction.Commit();
            Volatile.Write(ref _initialized, 1);
        }
    }

    private static void ValidateSchema(SqliteConnection connection, SqliteTransaction? transaction)
    {
        using (var tables = connection.CreateCommand())
        {
            tables.Transaction = transaction;
            tables.CommandText = "SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name;";
            using var reader = tables.ExecuteReader();
            if (!reader.Read()
                || !string.Equals(reader.GetString(0), "table", StringComparison.Ordinal)
                || !string.Equals(reader.GetString(1), TableName, StringComparison.Ordinal)
                || reader.Read())
            {
                throw new InvalidDataException("The plugin database contains unexpected schema objects.");
            }
        }

        var expectedColumns = new (string Name, string Type, bool NotNull, long PrimaryKeyOrder)[]
        {
            ("item_id", "TEXT", true, 1),
            ("source_key", "TEXT", true, 2),
            ("url_hash", "TEXT", true, 0),
            ("sha1", "TEXT", false, 0),
            ("file_size", "INTEGER", false, 0)
        };

        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = "PRAGMA table_info(strm_fingerprint);";
        using var columns = command.ExecuteReader();
        var index = 0;
        while (columns.Read())
        {
            if (index >= expectedColumns.Length)
            {
                throw new InvalidDataException("The plugin fingerprint table contains unexpected columns.");
            }

            var expected = expectedColumns[index++];
            if (!string.Equals(columns.GetString(1), expected.Name, StringComparison.Ordinal)
                || !string.Equals(columns.GetString(2), expected.Type, StringComparison.OrdinalIgnoreCase)
                || (columns.GetInt64(3) != 0) != expected.NotNull
                || columns.GetInt64(5) != expected.PrimaryKeyOrder)
            {
                throw new InvalidDataException("The plugin fingerprint table does not match the supported schema.");
            }
        }

        if (index != expectedColumns.Length)
        {
            throw new InvalidDataException("The plugin fingerprint table is incomplete.");
        }
    }

    private static int ReadUserVersion(SqliteConnection connection, SqliteTransaction transaction)
    {
        return checked((int)ExecuteScalarInt64(connection, transaction, "PRAGMA user_version;"));
    }

    private static long ExecuteScalarInt64(SqliteConnection connection, SqliteTransaction transaction, string sql)
    {
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = sql;
        return Convert.ToInt64(command.ExecuteScalar(), CultureInfo.InvariantCulture);
    }

    private static void ExecuteNonQuery(SqliteConnection connection, SqliteTransaction transaction, string sql)
    {
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = sql;
        command.ExecuteNonQuery();
    }

    private static StrmFingerprint? GetWithinTransaction(
        SqliteConnection connection,
        SqliteTransaction transaction,
        Guid itemId,
        string sourceKey)
    {
        using var command = connection.CreateCommand();
        command.Transaction = transaction;
        command.CommandText = "SELECT item_id, source_key, url_hash, sha1, file_size FROM strm_fingerprint WHERE item_id = $item_id AND source_key = $source_key;";
        command.Parameters.AddWithValue("$item_id", FormatId(itemId));
        command.Parameters.AddWithValue("$source_key", sourceKey);
        using var reader = command.ExecuteReader();
        return reader.Read() ? ReadFingerprint(reader, itemId, sourceKey) : null;
    }

    private static StrmFingerprint ReadFingerprint(SqliteDataReader reader, Guid expectedItemId, string expectedSourceKey)
    {
        var itemIdValue = reader.GetString(0);
        var sourceKeyValue = reader.GetString(1);
        if (!Guid.TryParseExact(itemIdValue, "N", out var storedItemId)
            || storedItemId != expectedItemId
            || !Guid.TryParseExact(sourceKeyValue, "N", out var storedSourceId)
            || !string.Equals(storedSourceId.ToString("N", CultureInfo.InvariantCulture), expectedSourceKey, StringComparison.Ordinal))
        {
            throw new InvalidDataException("The plugin fingerprint row has an invalid project or source identity.");
        }

        var urlHash = reader.GetString(2);
        var sha1 = reader.IsDBNull(3) ? null : reader.GetString(3);
        long? size = reader.IsDBNull(4) ? null : reader.GetInt64(4);
        if (!IsValidHex(urlHash, 64)
            || (sha1 is not null && !StrmManifestReader.IsValidSha1(sha1))
            || (size is not null && size < 0))
        {
            throw new InvalidDataException("The plugin fingerprint row contains invalid fingerprint data.");
        }

        return new StrmFingerprint(expectedItemId, expectedSourceKey, urlHash.ToLowerInvariant(), sha1?.ToLowerInvariant(), size);
    }

    private static void AddFingerprintParameters(SqliteCommand command, StrmFingerprint fingerprint)
    {
        command.Parameters.AddWithValue("$item_id", FormatId(fingerprint.ItemId));
        command.Parameters.AddWithValue("$source_key", fingerprint.SourceKey);
        command.Parameters.AddWithValue("$url_hash", fingerprint.UrlHash);
        command.Parameters.AddWithValue("$sha1", (object?)fingerprint.Sha1 ?? DBNull.Value);
        command.Parameters.AddWithValue("$file_size", (object?)fingerprint.Size ?? DBNull.Value);
    }

    private static StrmFingerprint NormalizeCandidate(StrmFingerprint fingerprint)
    {
        var sourceKey = NormalizeSourceKey(fingerprint.SourceKey);
        if (!IsValidHex(fingerprint.UrlHash, 64)
            || (fingerprint.Sha1 is not null && !StrmManifestReader.IsValidSha1(fingerprint.Sha1))
            || (fingerprint.Size is not null && fingerprint.Size < 0))
        {
            throw new ArgumentException("The candidate fingerprint is invalid.", nameof(fingerprint));
        }

        return fingerprint with
        {
            SourceKey = sourceKey,
            UrlHash = fingerprint.UrlHash.ToLowerInvariant(),
            Sha1 = fingerprint.Sha1?.ToLowerInvariant()
        };
    }

    private static string NormalizeSourceKey(string sourceKey)
    {
        if (!Guid.TryParse(sourceKey, out var sourceId))
        {
            throw new ArgumentException("A fingerprint source key must be the stable Jellyfin media source ID.", nameof(sourceKey));
        }

        return FormatId(sourceId);
    }

    private static string FormatId(Guid id)
    {
        return id.ToString("N", CultureInfo.InvariantCulture);
    }

    private static bool IsValidHex(string? value, int length)
    {
        if (value is null || value.Length != length)
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
}
