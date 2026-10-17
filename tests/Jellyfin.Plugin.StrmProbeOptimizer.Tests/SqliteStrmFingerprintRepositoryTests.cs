using System.Security.Cryptography;
using System.Text;
using Jellyfin.Plugin.StrmProbeOptimizer.Services;
using Microsoft.Data.Sqlite;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace Jellyfin.Plugin.StrmProbeOptimizer.Tests;

[TestClass]
public sealed class SqliteStrmFingerprintRepositoryTests
{
    private static readonly Guid ProjectId = Guid.Parse("481b116c-3c0d-4a08-97e8-7bc9204e4491");
    private static readonly Guid SourceId = Guid.Parse("a8c344f2-3a3c-466c-b06c-c03d6474e02b");
    private const string FirstUrl = "https://media.example.invalid/movie.mkv?sig=first-private-value";
    private const string SecondUrl = "https://media.example.invalid/movie.mkv?sig=second-private-value";
    private const string PrivatePath = "/srv/private/library/Movie.strm";

    [TestMethod]
    public void EmptyDatabaseCreatesOnlyVersionedMinimalSchemaAndReopensFingerprint()
    {
        using var fixture = new DatabaseFixture();
        var repository = fixture.Repository;
        var initial = Fingerprint(FirstUrl, "0123456789abcdef0123456789abcdef01234567", 42);

        Assert.IsNull(repository.Get(ProjectId, SourceId.ToString("N")));
        Assert.IsTrue(repository.TryCommit(initial, expectedPrevious: null));

        var reopened = new SqliteStrmFingerprintRepository(fixture.DatabasePath);
        Assert.AreEqual(initial, reopened.Get(ProjectId, SourceId.ToString("N")));
        AssertDatabaseSchema(fixture.DatabasePath);

        var databaseBytes = File.ReadAllBytes(fixture.DatabasePath);
        var serializedDatabase = Encoding.UTF8.GetString(databaseBytes);
        Assert.IsFalse(serializedDatabase.Contains(FirstUrl, StringComparison.Ordinal));
        Assert.IsFalse(serializedDatabase.Contains(PrivatePath, StringComparison.Ordinal));
    }

    [TestMethod]
    public void ConditionalCommitRejectsStaleBaselineAndPreservesLatestVersion()
    {
        using var fixture = new DatabaseFixture();
        var original = Fingerprint(FirstUrl, "0123456789abcdef0123456789abcdef01234567", 42);
        var current = Fingerprint(SecondUrl, "abcdef0123456789abcdef0123456789abcdef01", 84);
        var stale = Fingerprint(FirstUrl, null, 100);

        Assert.IsTrue(fixture.Repository.TryCommit(original, expectedPrevious: null));
        Assert.IsTrue(fixture.Repository.TryCommit(current, original));
        Assert.IsFalse(fixture.Repository.TryCommit(stale, original));
        Assert.AreEqual(current, fixture.Repository.Get(ProjectId, SourceId.ToString("N")));
    }

    [TestMethod]
    public void CompetingFirstInsertionsAcceptOnlyOneBaseline()
    {
        using var fixture = new DatabaseFixture();
        var firstRepository = fixture.Repository;
        var secondRepository = new SqliteStrmFingerprintRepository(fixture.DatabasePath);
        var first = Fingerprint(FirstUrl, null, 42);
        var second = Fingerprint(SecondUrl, null, 84);
        var accepted = 0;

        Parallel.Invoke(
            () => Interlocked.Add(ref accepted, firstRepository.TryCommit(first, expectedPrevious: null) ? 1 : 0),
            () => Interlocked.Add(ref accepted, secondRepository.TryCommit(second, expectedPrevious: null) ? 1 : 0));

        Assert.AreEqual(1, accepted);
        var saved = firstRepository.Get(ProjectId, SourceId.ToString("N"));
        Assert.IsTrue(Equals(saved, first) || Equals(saved, second));
    }

    [TestMethod]
    public void FailedSqlTransactionLeavesPreviouslyAcceptedFingerprintIntact()
    {
        using var fixture = new DatabaseFixture();
        var original = Fingerprint(FirstUrl, "0123456789abcdef0123456789abcdef01234567", 42);
        var changed = Fingerprint(SecondUrl, "abcdef0123456789abcdef0123456789abcdef01", 84);
        Assert.IsTrue(fixture.Repository.TryCommit(original, expectedPrevious: null));

        using (var connection = OpenConnection(fixture.DatabasePath))
        using (var command = connection.CreateCommand())
        {
            command.CommandText = "CREATE TRIGGER reject_fingerprint_update BEFORE UPDATE ON strm_fingerprint BEGIN SELECT RAISE(ABORT, 'injected transaction failure'); END;";
            command.ExecuteNonQuery();
        }

        AssertThrows<SqliteException>(() => fixture.Repository.TryCommit(changed, original));
        Assert.AreEqual(original, fixture.Repository.Get(ProjectId, SourceId.ToString("N")));
    }

    [TestMethod]
    public void UnknownAndUnversionedDatabasesAreRejectedWithoutReplacingExistingData()
    {
        using var fixture = new DatabaseFixture();
        var unknownRepository = new SqliteStrmFingerprintRepository(fixture.DatabasePath);
        using (var connection = OpenConnection(fixture.DatabasePath))
        using (var command = connection.CreateCommand())
        {
            command.CommandText = "PRAGMA user_version = 7; CREATE TABLE sentinel(value TEXT NOT NULL);";
            command.ExecuteNonQuery();
        }

        AssertThrows<InvalidDataException>(() => unknownRepository.Get(ProjectId, SourceId.ToString("N")));
        Assert.AreEqual(7, ReadUserVersion(fixture.DatabasePath));
        Assert.IsTrue(TableExists(fixture.DatabasePath, "sentinel"));

        using var unversionedFixture = new DatabaseFixture();
        var unversionedRepository = new SqliteStrmFingerprintRepository(unversionedFixture.DatabasePath);
        using (var connection = OpenConnection(unversionedFixture.DatabasePath))
        using (var command = connection.CreateCommand())
        {
            command.CommandText = "CREATE TABLE user_data(value TEXT NOT NULL);";
            command.ExecuteNonQuery();
        }

        AssertThrows<InvalidDataException>(() => unversionedRepository.Get(ProjectId, SourceId.ToString("N")));
        Assert.IsTrue(TableExists(unversionedFixture.DatabasePath, "user_data"));
        Assert.AreEqual(0, ReadUserVersion(unversionedFixture.DatabasePath));

        using var viewFixture = new DatabaseFixture();
        var viewRepository = new SqliteStrmFingerprintRepository(viewFixture.DatabasePath);
        using (var connection = OpenConnection(viewFixture.DatabasePath))
        using (var command = connection.CreateCommand())
        {
            command.CommandText = "CREATE VIEW user_view AS SELECT 1 AS value;";
            command.ExecuteNonQuery();
        }

        AssertThrows<InvalidDataException>(() => viewRepository.Get(ProjectId, SourceId.ToString("N")));
        Assert.IsTrue(ViewExists(viewFixture.DatabasePath, "user_view"));
        Assert.AreEqual(0, ReadUserVersion(viewFixture.DatabasePath));
    }

    [TestMethod]
    public void CorruptDatabaseIsRejectedWithoutReplacingOrDeletingIt()
    {
        using var fixture = new DatabaseFixture();
        var corruptBytes = new byte[512];
        new Random(20261013).NextBytes(corruptBytes);
        File.WriteAllBytes(fixture.DatabasePath, corruptBytes);
        var repository = new SqliteStrmFingerprintRepository(fixture.DatabasePath);

        AssertThrowsAny<SqliteException, InvalidDataException>(() => repository.Get(ProjectId, SourceId.ToString("N")));
        AssertThrowsAny<SqliteException, InvalidDataException>(() => repository.TryCommit(Fingerprint(FirstUrl, null, 42), expectedPrevious: null));

        CollectionAssert.AreEqual(corruptBytes, File.ReadAllBytes(fixture.DatabasePath), "A rejected corrupt database must be preserved, not deleted or rebuilt.");
        AssertThrowsAny<SqliteException, InvalidDataException>(() => TableExists(fixture.DatabasePath, "strm_fingerprint"));
    }

    [TestMethod]
    public void EmptyFileIsTreatedAsANewDatabaseAndNotMistakenForCorruption()
    {
        using var fixture = new DatabaseFixture();
        File.WriteAllBytes(fixture.DatabasePath, []);
        var repository = new SqliteStrmFingerprintRepository(fixture.DatabasePath);

        Assert.IsNull(repository.Get(ProjectId, SourceId.ToString("N")));
        Assert.IsTrue(repository.TryCommit(Fingerprint(FirstUrl, null, 42), expectedPrevious: null));
        AssertDatabaseSchema(fixture.DatabasePath);
    }

    private static StrmFingerprint Fingerprint(string url, string? sha1, long? size)
    {
        var urlHash = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(url))).ToLowerInvariant();
        return new StrmFingerprint(ProjectId, SourceId.ToString("N"), urlHash, sha1, size);
    }

    private static void AssertDatabaseSchema(string databasePath)
    {
        using var connection = OpenConnection(databasePath);
        using var versionCommand = connection.CreateCommand();
        versionCommand.CommandText = "PRAGMA user_version;";
        Assert.AreEqual(SqliteStrmFingerprintRepository.CurrentSchemaVersion, Convert.ToInt32(versionCommand.ExecuteScalar(), System.Globalization.CultureInfo.InvariantCulture));

        using var tableCommand = connection.CreateCommand();
        tableCommand.CommandText = "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%';";
        Assert.AreEqual("strm_fingerprint", tableCommand.ExecuteScalar());

        using var columnCommand = connection.CreateCommand();
        columnCommand.CommandText = "PRAGMA table_info(strm_fingerprint);";
        using var reader = columnCommand.ExecuteReader();
        var columns = new List<string>();
        while (reader.Read())
        {
            columns.Add(reader.GetString(1));
        }

        CollectionAssert.AreEqual(new[] { "item_id", "source_key", "url_hash", "sha1", "file_size" }, columns);
    }

    private static SqliteConnection OpenConnection(string path)
    {
        var connection = new SqliteConnection(new SqliteConnectionStringBuilder
        {
            DataSource = path,
            Pooling = false,
            DefaultTimeout = 30
        }.ToString());
        connection.Open();
        return connection;
    }

    private static int ReadUserVersion(string path)
    {
        using var connection = OpenConnection(path);
        using var command = connection.CreateCommand();
        command.CommandText = "PRAGMA user_version;";
        return Convert.ToInt32(command.ExecuteScalar(), System.Globalization.CultureInfo.InvariantCulture);
    }

    private static bool TableExists(string path, string name)
    {
        using var connection = OpenConnection(path);
        using var command = connection.CreateCommand();
        command.CommandText = "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = $name;";
        command.Parameters.AddWithValue("$name", name);
        return Convert.ToInt32(command.ExecuteScalar(), System.Globalization.CultureInfo.InvariantCulture) == 1;
    }

    private static bool ViewExists(string path, string name)
    {
        using var connection = OpenConnection(path);
        using var command = connection.CreateCommand();
        command.CommandText = "SELECT COUNT(*) FROM sqlite_master WHERE type = 'view' AND name = $name;";
        command.Parameters.AddWithValue("$name", name);
        return Convert.ToInt32(command.ExecuteScalar(), System.Globalization.CultureInfo.InvariantCulture) == 1;
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

    private static void AssertThrowsAny<TFirst, TSecond>(Action action)
        where TFirst : Exception
        where TSecond : Exception
    {
        try
        {
            action();
        }
        catch (Exception exception) when (exception is TFirst or TSecond)
        {
            return;
        }

        throw new AssertFailedException($"Expected {typeof(TFirst).Name} or {typeof(TSecond).Name}.");
    }

    private sealed class DatabaseFixture : IDisposable
    {
        private readonly string _directory = Path.Combine(Path.GetTempPath(), "strm-probe-sqlite-" + Guid.NewGuid().ToString("N"));

        public DatabaseFixture()
        {
            Directory.CreateDirectory(_directory);
            DatabasePath = Path.Combine(_directory, "strm-fingerprints.db");
            Repository = new SqliteStrmFingerprintRepository(DatabasePath);
        }

        public string DatabasePath { get; }

        public SqliteStrmFingerprintRepository Repository { get; }

        public void Dispose()
        {
            if (Directory.Exists(_directory))
            {
                Directory.Delete(_directory, recursive: true);
            }
        }
    }
}
