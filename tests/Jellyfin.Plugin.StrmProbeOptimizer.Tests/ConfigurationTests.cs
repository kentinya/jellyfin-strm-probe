using System.Xml.Serialization;
using Jellyfin.Plugin.StrmProbeOptimizer.Services;
using MediaBrowser.Common.Configuration;
using MediaBrowser.Model.Serialization;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace Jellyfin.Plugin.StrmProbeOptimizer.Tests;

[TestClass]
public sealed class ConfigurationTests
{
    [TestMethod]
    public void DefaultsMatchTheDocumentedCoreConfiguration()
    {
        var configuration = new PluginConfiguration();
        Assert.IsTrue(configuration.Enabled);
        Assert.IsTrue(configuration.PlaybackAutoCheck);
        Assert.AreEqual(PluginConfiguration.DefaultMaxConcurrentProbes, configuration.MaxConcurrentProbes);
        Assert.IsFalse(configuration.DetailedLog);
    }

    [TestMethod]
    public void LegacyConfigurationWithoutNewFieldsLoadsWithDefaults()
    {
        using var fixture = new PluginFixture();
        fixture.WriteLegacyConfiguration();

        var plugin = fixture.CreatePlugin();

        Assert.IsFalse(plugin.Configuration.PlaybackAutoCheck, "The legacy PlaybackAutoCheck value must be preserved.");
        Assert.IsTrue(plugin.Configuration.Enabled, "A missing Enabled field must default to true.");
        Assert.IsFalse(plugin.Configuration.DetailedLog, "A missing DetailedLog field must default to false.");
        Assert.AreEqual(PluginConfiguration.DefaultMaxConcurrentProbes, plugin.Configuration.MaxConcurrentProbes, "A missing MaxConcurrentProbes must default to 2.");
        Assert.AreEqual(PluginConfiguration.DefaultMaxConcurrentProbes, plugin.StartupMaxConcurrentProbes);
    }

    [TestMethod]
    public void PersistedInvalidConcurrencyFallsBackToTheDefaultStartupLimit()
    {
        using var fixture = new PluginFixture();
        fixture.WriteConfiguration(new PluginConfiguration { MaxConcurrentProbes = 9 });

        var plugin = fixture.CreatePlugin();

        Assert.AreEqual(PluginConfiguration.DefaultMaxConcurrentProbes, plugin.StartupMaxConcurrentProbes, "An invalid persisted configuration must not become the running limit.");
        Assert.AreEqual(9, plugin.Configuration.MaxConcurrentProbes, "The invalid persisted value must remain visible for diagnosis until it is corrected.");
    }

    [TestMethod]
    public void ValidConfigurationIsSavedAndBecomesEffective()
    {
        using var fixture = new PluginFixture();
        var plugin = fixture.CreatePlugin();
        var candidate = new PluginConfiguration
        {
            Enabled = false,
            PlaybackAutoCheck = false,
            MaxConcurrentProbes = 8,
            DetailedLog = true
        };

        plugin.UpdateConfiguration(candidate);

        Assert.AreSame(candidate, plugin.Configuration);
        var reloaded = fixture.ReadConfiguration();
        Assert.IsFalse(reloaded.Enabled);
        Assert.IsFalse(reloaded.PlaybackAutoCheck);
        Assert.AreEqual(8, reloaded.MaxConcurrentProbes);
        Assert.IsTrue(reloaded.DetailedLog);
    }

    [TestMethod]
    [DataRow(0)]
    [DataRow(9)]
    [DataRow(-1)]
    public void OutOfRangeConcurrencyIsRejectedWithoutChangingTheEffectiveConfigurationOrFile(int value)
    {
        using var fixture = new PluginFixture();
        var plugin = fixture.CreatePlugin();
        var before = plugin.Configuration;
        var fileBefore = fixture.ReadConfigurationFileBytes();

        Assert.ThrowsExactly<ArgumentException>(() =>
            plugin.UpdateConfiguration(new PluginConfiguration { MaxConcurrentProbes = value }));

        Assert.AreSame(before, plugin.Configuration, "A rejected configuration must not become effective.");
        CollectionAssert.AreEqual(fileBefore, fixture.ReadConfigurationFileBytes(), "A rejected configuration must not be persisted.");
    }

    [TestMethod]
    public void FailedPersistenceDoesNotPublishTheCandidateConfiguration()
    {
        using var fixture = new PluginFixture();
        var plugin = fixture.CreatePlugin();
        var before = plugin.Configuration;
        var fileBefore = fixture.ReadConfigurationFileBytes();
        fixture.Serializer.FailSerialize = true;

        Assert.ThrowsExactly<IOException>(() =>
            plugin.UpdateConfiguration(new PluginConfiguration { Enabled = false, MaxConcurrentProbes = 7 }));

        Assert.AreSame(before, plugin.Configuration, "A failed save must leave the previously effective configuration in place.");
        CollectionAssert.AreEqual(fileBefore, fixture.ReadConfigurationFileBytes(), "A failed save must not write a partial configuration file.");
    }

    [TestMethod]
    public void LatePersistenceFailureKeepsThePreviouslySavedFileAndEffectiveConfiguration()
    {
        using var fixture = new PluginFixture();
        var saved = new PluginConfiguration { Enabled = false, PlaybackAutoCheck = true, MaxConcurrentProbes = 6, DetailedLog = true };
        fixture.WriteConfiguration(saved);
        var plugin = fixture.CreatePlugin();
        var effective = plugin.Configuration;
        var fileBefore = fixture.ReadConfigurationFileBytes();

        // The native serializer opens and truncates the destination before serializing. A failure after the
        // open/write boundary must not damage the previously valid configuration file.
        fixture.Serializer.FailAfterPartialWrite = true;
        Assert.ThrowsExactly<IOException>(() =>
            plugin.UpdateConfiguration(new PluginConfiguration { Enabled = true, MaxConcurrentProbes = 7 }));

        Assert.AreSame(effective, plugin.Configuration, "A mid-write failure must leave the previously effective configuration in place.");
        CollectionAssert.AreEqual(fileBefore, fixture.ReadConfigurationFileBytes(), "A mid-write failure must not damage the previously saved configuration file.");

        // A later restart re-loads the still-valid previous configuration rather than a truncated candidate.
        var reloaded = fixture.CreatePlugin();
        Assert.IsFalse(reloaded.Configuration.Enabled, "The previous valid disabled configuration must survive the failed save.");
        Assert.AreEqual(6, reloaded.Configuration.MaxConcurrentProbes);
        Assert.IsTrue(reloaded.Configuration.DetailedLog);

        // A subsequent valid save replaces the file atomically and persists the repaired configuration.
        fixture.Serializer.FailAfterPartialWrite = false;
        reloaded.UpdateConfiguration(new PluginConfiguration { Enabled = true, PlaybackAutoCheck = true, MaxConcurrentProbes = 4, DetailedLog = false });
        var repaired = fixture.ReadConfiguration();
        Assert.IsTrue(repaired.Enabled);
        Assert.AreEqual(4, repaired.MaxConcurrentProbes);
        Assert.IsFalse(repaired.DetailedLog);
    }

    [TestMethod]
    public void InvalidPersistedConfigurationDiagnosticDoesNotLeakPrivatePaths()
    {
        using var fixture = new PluginFixture();
        fixture.WriteConfiguration(new PluginConfiguration { MaxConcurrentProbes = 9 });
        var logger = new CapturingLogger<Plugin>();

        var plugin = new Plugin(fixture.Paths, fixture.Serializer, logger);

        Assert.AreEqual(PluginConfiguration.DefaultMaxConcurrentProbes, plugin.StartupMaxConcurrentProbes);
        Assert.IsTrue(logger.Messages.Any(message => message.Contains("invalid", StringComparison.OrdinalIgnoreCase)), "The invalid configuration must still produce an actionable diagnostic.");
        Assert.IsFalse(logger.Messages.Any(message => message.Contains(fixture.ConfigurationFilePath, StringComparison.Ordinal)), "The diagnostic must not contain the private configuration file path.");
        Assert.IsFalse(logger.Messages.Any(message => message.Contains(fixture.Paths.PluginConfigurationsPath, StringComparison.Ordinal)), "The diagnostic must not contain the private configuration directory.");
    }

    [TestMethod]
    public void PluginPlaybackSettingsReadTheStartupLimitAndLiveValues()
    {
        using var fixture = new PluginFixture();
        fixture.WriteConfiguration(new PluginConfiguration
        {
            Enabled = false,
            PlaybackAutoCheck = false,
            MaxConcurrentProbes = 6,
            DetailedLog = true
        });
        var plugin = fixture.CreatePlugin();
        var settings = new PluginPlaybackSettings();

        Assert.IsFalse(settings.Enabled);
        Assert.IsFalse(settings.PlaybackAutoCheck);
        Assert.IsTrue(settings.DetailedLog);
        Assert.AreEqual(6, settings.MaxConcurrentProbes, "The running pool must consume the real saved configuration captured at startup.");

        plugin.UpdateConfiguration(new PluginConfiguration { Enabled = true, PlaybackAutoCheck = true, MaxConcurrentProbes = 3, DetailedLog = false });
        Assert.IsTrue(settings.Enabled, "Enable and playback check apply to the next check request.");
        Assert.IsTrue(settings.PlaybackAutoCheck);
        Assert.IsFalse(settings.DetailedLog);
        Assert.AreEqual(6, settings.MaxConcurrentProbes, "A saved concurrency change must only apply after the next restart.");
    }

    private sealed class PluginFixture : IDisposable
    {
        private readonly string _root;

        public PluginFixture()
        {
            _root = Path.Combine(Path.GetTempPath(), "strm-probe-config-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(Path.Combine(_root, "plugins"));
            Directory.CreateDirectory(Path.Combine(_root, "plugins", "configurations"));
            Paths = new TestApplicationPaths(_root);
            Serializer = new TestXmlSerializer();
        }

        public TestApplicationPaths Paths { get; }

        public TestXmlSerializer Serializer { get; }

        public string ConfigurationFilePath => System.IO.Path.Combine(_root, "plugins", "configurations", "Jellyfin.Plugin.StrmProbeOptimizer.xml");

        public Plugin CreatePlugin()
        {
            return new Plugin(Paths, Serializer, NullLogger<Plugin>.Instance);
        }

        public void WriteLegacyConfiguration()
        {
            File.WriteAllText(
                ConfigurationFilePath,
                "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n<PluginConfiguration xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\" xmlns:xsd=\"http://www.w3.org/2001/XMLSchema\">\n  <PlaybackAutoCheck>false</PlaybackAutoCheck>\n</PluginConfiguration>\n");
        }

        public void WriteConfiguration(PluginConfiguration configuration)
        {
            using var stream = File.Create(ConfigurationFilePath);
            new XmlSerializer(typeof(PluginConfiguration)).Serialize(stream, configuration);
        }

        public PluginConfiguration ReadConfiguration()
        {
            using var stream = File.OpenRead(ConfigurationFilePath);
            return (PluginConfiguration)new XmlSerializer(typeof(PluginConfiguration)).Deserialize(stream)!;
        }

        public byte[] ReadConfigurationFileBytes()
        {
            return File.Exists(ConfigurationFilePath) ? File.ReadAllBytes(ConfigurationFilePath) : [];
        }

        public void Dispose()
        {
            try
            {
                Directory.Delete(_root, recursive: true);
            }
            catch (IOException)
            {
                // Best effort cleanup of the temporary configuration directory.
            }
        }
    }

    private sealed class TestXmlSerializer : IXmlSerializer
    {
        public bool FailSerialize { get; set; }

        public bool FailAfterPartialWrite { get; set; }

        public object DeserializeFromStream(Type type, Stream stream)
        {
            return new XmlSerializer(type).Deserialize(stream)!;
        }

        public object DeserializeFromFile(Type type, string file)
        {
            if (!File.Exists(file))
            {
                throw new FileNotFoundException("No persisted configuration.", file);
            }

            using var stream = File.OpenRead(file);
            return new XmlSerializer(type).Deserialize(stream)!;
        }

        public object DeserializeFromBytes(Type type, byte[] buffer)
        {
            using var stream = new MemoryStream(buffer);
            return new XmlSerializer(type).Deserialize(stream)!;
        }

        public void SerializeToStream(object obj, Stream stream)
        {
            if (FailSerialize)
            {
                throw new IOException("Injected configuration serialization failure.");
            }

            new XmlSerializer(obj.GetType()).Serialize(stream, obj);
        }

        public void SerializeToFile(object obj, string file)
        {
            if (FailSerialize)
            {
                throw new IOException("Injected configuration serialization failure.");
            }

            using var stream = File.Create(file);
            if (FailAfterPartialWrite)
            {
                // Match the native serializer's FileMode.Create truncation boundary, then fail mid-write.
                stream.Write("<PluginConfiguration>"u8);
                stream.Flush();
                throw new IOException("Injected configuration write failure after truncation and partial write.");
            }

            new XmlSerializer(obj.GetType()).Serialize(stream, obj);
        }
    }

    private sealed class CapturingLogger<T> : ILogger<T>
    {
        public List<string> Messages { get; } = [];

        public IDisposable? BeginScope<TState>(TState state)
            where TState : notnull
        {
            return null;
        }

        public bool IsEnabled(LogLevel logLevel)
        {
            return true;
        }

        public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception, Func<TState, Exception?, string> formatter)
        {
            Messages.Add(formatter(state, exception));
        }
    }

    private sealed class TestApplicationPaths : IApplicationPaths
    {
        public TestApplicationPaths(string root)
        {
            DataPath = Path.Combine(root, "data");
            PluginsPath = Path.Combine(root, "plugins");
            PluginConfigurationsPath = Path.Combine(root, "plugins", "configurations");
            Directory.CreateDirectory(DataPath);
            Directory.CreateDirectory(PluginConfigurationsPath);
        }

        public string ProgramDataPath => DataPath;

        public string WebPath => string.Empty;

        public string ProgramSystemPath => string.Empty;

        public string DataPath { get; }

        public string ImageCachePath => Path.Combine(DataPath, "images");

        public string PluginsPath { get; }

        public string PluginConfigurationsPath { get; }

        public string LogDirectoryPath => Path.Combine(DataPath, "log");

        public string ConfigurationDirectoryPath => DataPath;

        public string SystemConfigurationFilePath => Path.Combine(DataPath, "system.xml");

        public string CachePath => Path.Combine(DataPath, "cache");

        public string TempDirectory => Path.Combine(DataPath, "temp");

        public string VirtualDataPath => DataPath;

        public string TrickplayPath => Path.Combine(DataPath, "trickplay");

        public string BackupPath => Path.Combine(DataPath, "backups");

        public void MakeSanityCheckOrThrow()
        {
        }

        public void CreateAndCheckMarker(string path, string markerName, bool recursive = false)
        {
        }
    }
}
