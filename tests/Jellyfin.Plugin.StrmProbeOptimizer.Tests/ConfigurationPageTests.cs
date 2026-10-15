using System.Reflection;
using System.Text.RegularExpressions;
using Jellyfin.Plugin.StrmProbeOptimizer;
using MediaBrowser.Model.Plugins;
using Microsoft.VisualStudio.TestTools.UnitTesting;

namespace Jellyfin.Plugin.StrmProbeOptimizer.Tests;

[TestClass]
public sealed class ConfigurationPageTests
{
    private static readonly Assembly PluginAssembly = typeof(Plugin).Assembly;

    [TestMethod]
    public void GetPagesExposesExactlyOnePageWithAnExistingEmbeddedResource()
    {
        var plugin = (IHasWebPages)CreatePlugin();
        var descriptors = plugin.GetPages().ToArray();

        Assert.HasCount(1, descriptors, "The plugin must expose exactly one configuration page.");
        var page = descriptors[0];
        Assert.AreEqual("StrmProbeOptimizer", page.Name);
        Assert.IsFalse(page.EnableInMainMenu, "The page is opened from the plugin entry, not as a separate main-menu item.");

        using var stream = PluginAssembly.GetManifestResourceStream(page.EmbeddedResourcePath);
        Assert.IsNotNull(stream, $"The embedded resource {page.EmbeddedResourcePath} must exist in the plugin assembly.");
        using var reader = new StreamReader(stream);
        var html = reader.ReadToEnd();
        Assert.IsGreaterThan(0, html.Length, "The configuration page resource must not be empty.");
    }

    [TestMethod]
    public void PageExposesTheFiveEditableConfigurationFields()
    {
        var html = ReadPage();

        foreach (var id in new[] { "Enabled", "PlaybackAutoCheck", "MaxConcurrentProbes", "DetailedLog", "BatchAllLibraries" })
        {
            Assert.Contains($"id=\"{id}\"", html, $"The page must expose the {id} field.");
        }

        Assert.Contains("getPluginConfiguration", html, "The page must load the saved configuration through the existing channel.");
        Assert.Contains("updatePluginConfiguration", html, "The page must save through the existing channel.");
    }

    [TestMethod]
    public void PagePointsAtTheNativeScheduledTaskWithoutASecondRunOrStopEntry()
    {
        var html = ReadPage();

        Assert.Contains("计划任务", html, "The page must guide the administrator to the native scheduled task page.");
        Assert.Contains("STRM 媒体信息检查", html, "The page must name the native task.");
        // The page must not offer its own run/stop/schedule controls or call a task-running endpoint directly.
        Assert.DoesNotContain("ScheduledTasks/Running", html, "The page must not start or stop the native task itself.");
        Assert.DoesNotContain("RunTask", html, "The page must not add an independent run button.");
        Assert.DoesNotContain("TaskTriggerInfo", html, "The page must not schedule the task itself.");
    }

    [TestMethod]
    public void PageResourceDoesNotLeakSecretsOrPrivatePaths()
    {
        var html = ReadPage();

        foreach (var forbidden in new[] { "Token=", "Cookie", "Authorization", "password", "C:\\", "/src/", "/opt/", "MediaBrowser Token" })
        {
            Assert.DoesNotContain(forbidden, html, $"The page must not contain the secret or private marker {forbidden}.");
        }

        Assert.IsFalse(
            Regex.IsMatch(html, @"https?://", RegexOptions.IgnoreCase),
            "The configuration page must not embed a concrete media or signed URL.");
    }

    [TestMethod]
    public void PageDocumentsTheFixedRulesAndRecoveryWithoutACloseSwitch()
    {
        var html = ReadPage();

        Assert.Contains("不升级", html, "The page must state that allowMediaProbe=false is never elevated.");
        Assert.Contains("修改时间", html, "The page must state that mtime does not trigger a probe.");
        Assert.Contains("首次信任", html, "The page must describe the first-trust rule.");
        Assert.Contains("strm-fingerprints.db", html, "The page must describe how to recover the state store.");
        Assert.Contains("下一次 Jellyfin 启动", html, "The page must state when the concurrency change applies.");
    }

    [TestMethod]
    public void PageSurfacesStaleLibrariesAndBlocksUntilCorrected()
    {
        var html = ReadPage();

        Assert.Contains("data-stale", html, "The page must mark a saved-but-missing library so it is never silently dropped.");
        Assert.Contains("已失效媒体库", html, "The page must label a stale saved library.");
        Assert.Contains("不会保存为全部", html, "The page must state an empty or invalid explicit scope is never widened to all libraries.");
    }

    [TestMethod]
    public void PageDistinguishesRejectionFromUnconfirmedSaveAndOffersReload()
    {
        var html = ReadPage();

        Assert.Contains("保存被拒绝", html, "The page must report a confirmed rejection distinctly.");
        Assert.Contains("保存结果未确认", html, "The page must not promise a rollback when the save result is unknown.");
        Assert.DoesNotContain("已保存的有效配置未被更改", html, "The page must not claim the effective configuration was unchanged on a network failure.");
        Assert.Contains("ReloadConfiguration", html, "The page must offer a reload action after an unconfirmed or failed result.");
    }

    [TestMethod]
    public void PageDeclaresTheFormAsClientValidated()
    {
        var html = ReadPage();

        // The native number input's max attribute would block the submit event before the page's own validation
        // feedback runs, so the form is explicitly novalidate and the page reports the actionable message itself.
        Assert.Contains("novalidate", html, "The page must own its validation feedback instead of the browser's native constraint UI.");
    }

    [TestMethod]
    public void PageValidatesTheWholeConcurrencyNumberWithoutTruncating()
    {
        var html = ReadPage();

        // FR-U4: parseInt would silently turn "2.5" into 2 and "1e1" into 1 and then save a different value than
        // the one shown. The page must read the full number and require an integer in range before saving.
        Assert.Contains("valueAsNumber", html, "The page must read the full number the administrator typed.");
        Assert.Contains("Number.isInteger", html, "The page must require an integer concurrency value.");
        Assert.DoesNotContain("parseInt(concurrencyInput", html, "The page must not truncate the concurrency input with parseInt.");
    }

    private static string ReadPage()
    {
        var plugin = (IHasWebPages)CreatePlugin();
        var page = plugin.GetPages().Single();
        using var stream = PluginAssembly.GetManifestResourceStream(page.EmbeddedResourcePath);
        Assert.IsNotNull(stream);
        using var reader = new StreamReader(stream);
        return reader.ReadToEnd();
    }

    private static Plugin CreatePlugin()
    {
        var root = Path.Combine(Path.GetTempPath(), "strm-probe-page-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(Path.Combine(root, "plugins", "configurations"));
        return new Plugin(new MinimalApplicationPaths(root), new XmlSerializer(), Microsoft.Extensions.Logging.Abstractions.NullLogger<Plugin>.Instance);
    }

    private sealed class XmlSerializer : MediaBrowser.Model.Serialization.IXmlSerializer
    {
        public object DeserializeFromStream(Type type, Stream stream) => new System.Xml.Serialization.XmlSerializer(type).Deserialize(stream)!;

        public object DeserializeFromFile(Type type, string file)
        {
            if (!File.Exists(file))
            {
                throw new FileNotFoundException("No persisted configuration.", file);
            }

            using var stream = File.OpenRead(file);
            return new System.Xml.Serialization.XmlSerializer(type).Deserialize(stream)!;
        }

        public object DeserializeFromBytes(Type type, byte[] buffer)
        {
            using var stream = new MemoryStream(buffer);
            return new System.Xml.Serialization.XmlSerializer(type).Deserialize(stream)!;
        }

        public void SerializeToStream(object obj, Stream stream) => new System.Xml.Serialization.XmlSerializer(obj.GetType()).Serialize(stream, obj);

        public void SerializeToFile(object obj, string file)
        {
            using var stream = File.Create(file);
            new System.Xml.Serialization.XmlSerializer(obj.GetType()).Serialize(stream, obj);
        }
    }

    private sealed class MinimalApplicationPaths : MediaBrowser.Common.Configuration.IApplicationPaths
    {
        public MinimalApplicationPaths(string root)
        {
            DataPath = Path.Combine(root, "data");
            PluginsPath = Path.Combine(root, "plugins");
            PluginConfigurationsPath = Path.Combine(root, "plugins", "configurations");
            Directory.CreateDirectory(DataPath);
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
