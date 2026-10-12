---
title: "Jellyfin STRM Probe Optimizer 完整开发方案 V3.0"
---


# 一、插件的最终目标

插件名称建议：

`Jellyfin.Plugin.StrmProbeOptimizer`

主要解决三个问题。

### 1. STRM 每次播放重复 ffprobe

目前 Jellyfin 的 `GetPlaybackMediaSources()` 在允许探测的情况下，对 `.strm` 文件存在强制重新探测的逻辑。

即使数据库已经保存了视频编码、分辨率、时长等信息，仍可能在播放时触发远程探测。

插件要做到：

**媒体没有变化、数据库中已有必要媒体流，就跳过 ffprobe。**

### 2. STRM URL 不变，但远程视频被替换

通过修改 STRM 生成程序，在 STRM 文件中加入媒体内容版本标记。

例如：

```text
# strm-probe-version:1
# strm-probe-sha1:AABBCCDDEEFF0011223344556677889900112233
# strm-probe-size:10737418240
https://openlist.example.com/d/115/Movies/movie.mkv
```

当远程视频替换时，生成程序重新计算版本信息。

即使 URL 不变，插件也能发现 SHA-1 或文件大小发生变化。

### 3. URL 变化但视频内容相同

例如影片在 OpenList 中移动：

```text
旧：
https://openlist.example.com/d/Movies/movie.mkv

新：
https://openlist.example.com/d/Movies2/movie.mkv
```

如果 SHA-1 相同：

- 不重新 ffprobe。
- 同步 Jellyfin 的 `ShortcutPath`。
- PlaybackInfo 返回新 URL。
- 原有媒体流信息继续使用。

这是本方案的另一项重要优化。

---

# 二、最终业务判断规则

这部分作为开发时不可随意修改的规则。

## 2.1 完整判断表

| STRM URL | 新旧 SHA-1 | 文件大小 | 是否 ffprobe | 额外操作 |
|---|---|---|---|---|
| 不变 | 相同 | 任意 | ❌ | 复用媒体流 |
| 不变 | 不同 | 任意 | ✅ | 更新媒体流 |
| 不变 | 无法比较 | 相同 | ❌ | 复用媒体流 |
| 不变 | 无法比较 | 不同 | ✅ | 更新媒体流 |
| 不变 | 无法比较 | 无法比较 | ❌ | 记录信息不足 |
| **改变** | **相同** | **任意** | ❌ | 更新播放 URL |
| **改变** | **不同** | **任意** | ✅ | 更新 URL 和媒体流 |
| **改变** | **无法比较** | **任意** | ✅ | 更新 URL 和媒体流 |
| 任意 | 任意 | 仅修改时间变化 | ❌ | 忽略修改时间 |

这里有三个前提：

1. SHA-1 相同或不同，必须是**新旧两个有效 SHA-1**之间的比较。
2. 表格默认 Jellyfin 已经保存必要的主媒体流。否则仍需要探测。
3. 最后一行表示修改时间**本身**不能触发探测，不覆盖其他变化规则。

## 2.2 优先级

最终判断顺序：

```text
开始
 │
 ▼
是否为 STRM？
 │
 ├── 否 → Jellyfin 原生处理
 │
 ▼
解析 STRM URL、SHA-1、Size
 │
 ▼
Jellyfin 是否已有必要媒体流？
 │
 ├── 否 → ffprobe
 │
 ▼
URL 是否变化？
 │
 ├── 是
 │    │
 │    ▼
 │   新旧 SHA-1 是否有效且相同？
 │    │
 │    ├── 是 → 更新 URL，跳过 ffprobe
 │    │
 │    └── 否 → ffprobe
 │
 ▼
URL 没变化
 │
 ▼
新旧 SHA-1 是否都有效？
 │
 ├── 是
 │    │
 │    ├── 相同 → 跳过 ffprobe
 │    │
 │    └── 不同 → ffprobe
 │
 ▼
无法比较 SHA-1
 │
 ▼
文件大小是否变化？
 │
 ├── 是 → ffprobe
 │
 └── 否 → 跳过 ffprobe
```

**文件修改时间完全不参与这个决策。**

另外，如果原始调用的 `allowMediaProbe=false`，插件不得擅自启动 ffprobe。需要重新探测的状态应保留，等待允许探测的调用。

---

# 三、STRM 文件格式设计

## 3.1 推荐格式

```text
# strm-probe-version:1
# strm-probe-sha1:AABBCCDDEEFF0011223344556677889900112233
# strm-probe-size:10737418240
https://openlist.example.com/d/115/Movies/movie.mkv
```

字段定义：

| 字段 | 类型 | 含义 |
|---|---|---|
| `strm-probe-version` | 整数 | 插件解析协议版本 |
| `strm-probe-sha1` | 字符串 | 远程视频的 SHA-1 |
| `strm-probe-size` | 整数 | 视频大小，单位字节 |
| URL | 字符串 | Jellyfin 实际播放地址 |

这里的 `version:1` 是**协议版本**，不是文件修改次数，也不是每次生成都会增加的数字。

## 3.2 没有 SHA-1

```text
# strm-probe-version:1
# strm-probe-size:10737418240
https://openlist.example.com/d/115/Movies/movie.mkv
```

插件会使用 URL 和 Size 判断。

特别注意：

如果没有 SHA-1，而 URL 发生变化：

**即使 Size 相同，也必须 ffprobe。**

## 3.3 没有 Size

```text
# strm-probe-version:1
# strm-probe-sha1:AABBCCDDEEFF0011223344556677889900112233
https://openlist.example.com/d/115/Movies/movie.mkv
```

仍然可以通过 SHA-1 判断。

## 3.4 SHA-1 和 Size 都没有

```text
# strm-probe-version:1
https://openlist.example.com/d/115/Movies/movie.mkv
```

处理规则：

- URL 不变、已有主媒体流：跳过 ffprobe。
- URL 变化：ffprobe。
- 缺少主媒体流：ffprobe。

这属于性能优先的兼容模式，无法发现同 URL、同大小的远程视频替换。

## 3.5 为什么用注释？

我核对了 Jellyfin v12.2 的源码。

`ProbeProvider.FetchShortcutInfo()` 会忽略以 `#` 开头的行，读取第一个有效 URL。

因此，这种格式不需要修改 Jellyfin 原生 STRM 解析器。

源码：

[Jellyfin ProbeProvider.cs](https://github.com/jellyfin/jellyfin/blob/v12.2/MediaBrowser.Providers/MediaInfo/ProbeProvider.cs)

但正式发布前仍应测试不同 Jellyfin 客户端及可能直接读取 STRM 的第三方程序。

---

# 四、STRM 生成程序的开发方案

生成程序负责从 OpenList 获取媒体文件信息，然后写入 STRM。

## 4.1 生成流程

```text
OpenList 文件列表
        │
        ▼
获取文件路径
        │
        ▼
获取 SHA-1、Size
        │
        ▼
生成固定的 OpenList 播放 URL
        │
        ▼
构造 STRM 内容
        │
        ▼
比较本地现有 STRM
        │
        ├── 完全相同 → 不写入
        │
        └── 不同 → 原子替换 STRM
```

OpenList 的文件详情、文件列表接口均有相应元数据字段，具体取决于存储驱动是否提供。

源码：

[OpenList fsread.go](https://github.com/OpenListTeam/OpenList/blob/main/server/handles/fsread.go)

## 4.2 SHA-1 获取规则

优先使用 OpenList 返回的：

```json
{
  "hash_info": {
    "sha1": "..."
  }
}
```

需要校验 SHA-1：

- 必须是字符串。
- 必须为 40 位十六进制字符。
- 统一转换为小写或大写。
- 空字符串和非法值视为缺失。

不使用 URL 的 SHA-1 冒充媒体内容 SHA-1。

## 4.3 Size 规则

如果 OpenList 返回有效文件大小：

```json
{
  "size": 10737418240
}
```

则写入：

```text
# strm-probe-size:10737418240
```

Size 使用字节数，不能使用经过四舍五入的 GB、MB。

缺失的 Size 不能写成 `0`，否则可能造成错误变化判断。

## 4.4 修改时间规则

生成程序不需要把 `modified` 写入 STRM。

例如：

```text
原文件：
SHA-1 = AAA
Size = 1000
Modified = 10:00

新文件：
SHA-1 = AAA
Size = 1000
Modified = 15:00
```

生成的 STRM 内容完全相同。

不修改文件，也不触发 ffprobe。

## 4.5 URL 规则

建议生成稳定的 OpenList URL：

```text
https://openlist.example.com/d/115/Movies/movie.mkv
```

不要优先使用带临时签名的网盘直链：

```text
https://download.example.com/video?token=xxx
```

特别是没有 SHA-1 的情况下，签名 URL 每次变化都会按照既定规则触发 ffprobe。

所以，生成程序应尽可能保证：

**同一个 OpenList 文件位置对应稳定的 STRM URL。**

## 4.6 原子写入

生成程序不要使用：

```text
删除旧 STRM
    ↓
等待
    ↓
写入新 STRM
```

建议：

```text
构造新内容
    ↓
与旧内容比较
    ↓
需要更新
    ↓
写入同目录临时文件
    ↓
flush
    ↓
原子替换正式 STRM
```

这样可以降低 Jellyfin 读取到半个 STRM 或误判文件被删除的风险。

跨文件系统移动不一定具备原子性，因此临时文件应放在目标文件相同的文件系统中。

---

# 五、Jellyfin 插件架构

建议采用以下目录结构：

```text
Jellyfin.Plugin.StrmProbeOptimizer/
│
├── Plugin.cs
├── PluginConfiguration.cs
├── ServiceRegistrator.cs
│
├── Interceptors/
│   └── OptimizedMediaSourceManager.cs
│
├── Services/
│   ├── StrmManifestReader.cs
│   ├── StrmManifestParser.cs
│   ├── ProbeDecisionService.cs
│   ├── ProbeCoordinator.cs
│   ├── ProbeExecutor.cs
│   ├── ProbeResultValidator.cs
│   └── ShortcutPathSynchronizer.cs
│
├── Models/
│   ├── StrmManifest.cs
│   ├── MediaFingerprint.cs
│   ├── ProbeDecision.cs
│   └── ProbeState.cs
│
├── Persistence/
│   └── SqliteProbeStateRepository.cs
│
├── Configuration/
│   └── ConfigurationPage.html
│
└── Tests/
    ├── ManifestParserTests.cs
    ├── ProbeDecisionTests.cs
    ├── ProbeCoordinatorTests.cs
    ├── ShortcutPathTests.cs
    └── PlaybackIntegrationTests.cs
```

插件划分为七个核心模块。

| 模块 | 职责 |
|---|---|
| `StrmManifestReader` | 读取 STRM |
| `StrmManifestParser` | 解析 URL、SHA-1、Size |
| `ProbeDecisionService` | 判断是否 ffprobe |
| `ProbeCoordinator` | 并发控制 |
| `ProbeExecutor` | 调用 Jellyfin 原生探测 |
| `ProbeResultValidator` | 确认探测结果 |
| `ShortcutPathSynchronizer` | 同步最新播放地址 |

另由 SQLite 保存必要的状态。

---

# 六、插件怎么拦截 ffprobe？

这是开发的核心技术部分。

## 6.1 接入点

根据 Jellyfin v12.2 源码：

```csharp
IMediaSourceManager.GetPlaybackMediaSources(...)
```

是 PlaybackInfo 获取媒体源的重要入口。

内部原有逻辑包含：

```csharp
if (allowMediaProbe &&
    ...
    item.Path.EndsWith(".strm", ...))
{
    await item.RefreshMetadata(...);
}
```

源码：

[MediaSourceManager.cs](https://github.com/jellyfin/jellyfin/blob/v12.2/Emby.Server.Implementations/Library/MediaSourceManager.cs#L177-L205)

计划通过：

```csharp
IPluginServiceRegistrator
```

包装 `IMediaSourceManager`。

插件注册时保留原始 `MediaSourceManager` 实例，并在外层增加探测决策。

**重要限制：替换核心服务并不是 Jellyfin 明确承诺稳定的插件扩展机制。**

这套方案技术上有可研究的注册入口，但必须先完成运行原型验证。

尤其要保证：

- 原始服务只有一个有效实例。
- 不出现循环依赖。
- 不重复释放原始服务。
- `IMediaSourceManager` 的所有其他方法正常委托。
- Jellyfin 启动、关闭、直播和普通媒体播放不受影响。

## 6.2 跳过 ffprobe

当插件判断不需要探测：

```csharp
return await _inner.GetPlaybackMediaSources(
    item,
    user,
    allowMediaProbe: false,
    enablePathSubstitution,
    cancellationToken);
```

这样绕过原生实现中由 `allowMediaProbe` 控制的强制远程刷新。

仍使用 Jellyfin 原生媒体源生成逻辑。

## 6.3 需要 ffprobe

当检测到媒体变化时，不能仅仅调用：

```csharp
allowMediaProbe: true
```

因为未来 Jellyfin 可能合并 PR #17050。

届时即使媒体流信息是旧的，只要主媒体流存在，Jellyfin 也可能跳过探测。

因此建议显式调用原生刷新：

```csharp
await item.RefreshMetadata(
    new MetadataRefreshOptions(directoryService)
    {
        EnableRemoteContentProbe = true,
        MetadataRefreshMode = MetadataRefreshMode.FullRefresh
    },
    cancellationToken);
```

刷新后重新获取媒体源：

```csharp
return await _inner.GetPlaybackMediaSources(
    item,
    user,
    false,
    enablePathSubstitution,
    cancellationToken);
```

这段代码是实现方向，尚不是经过验证的完整插件代码。

另外，`FullRefresh` 可能运行其他元数据提供器，不只执行 ffprobe。后续需要评估额外开销，以及是否存在更精确的可用探测入口。

---

# 七、最关键的决策模块

建议统一定义：

```csharp
public enum ProbeDecision
{
    SkipProbe,
    RequireProbe,
    UpdatePathOnly,
    FallbackToJellyfin
}
```

含义：

| 决策 | 行为 |
|---|---|
| `SkipProbe` | 直接复用媒体流 |
| `RequireProbe` | 执行远程媒体探测 |
| `UpdatePathOnly` | 只更新播放 URL |
| `FallbackToJellyfin` | 不支持或无法安全处理 |

## 核心伪代码

```csharp
ProbeDecision Decide(
    MediaFingerprint oldMedia,
    MediaFingerprint newMedia,
    bool hasPrimaryStream)
{
    if (!hasPrimaryStream)
    {
        return ProbeDecision.RequireProbe;
    }

    bool urlChanged =
        oldMedia.UrlHash != newMedia.UrlHash;

    bool hasComparableSha1 =
        IsValidSha1(oldMedia.Sha1) &&
        IsValidSha1(newMedia.Sha1);

    // 优先判断 URL 是否变化
    if (urlChanged)
    {
        if (hasComparableSha1 &&
            Sha1Equals(oldMedia.Sha1, newMedia.Sha1))
        {
            return ProbeDecision.UpdatePathOnly;
        }

        // URL 变化、SHA-1 不同或者无法比较
        return ProbeDecision.RequireProbe;
    }

    // URL 不变，优先使用 SHA-1
    if (hasComparableSha1)
    {
        if (Sha1Equals(oldMedia.Sha1, newMedia.Sha1))
        {
            return ProbeDecision.SkipProbe;
        }

        return ProbeDecision.RequireProbe;
    }

    // 无法比较 SHA-1，使用文件大小
    if (oldMedia.Size.HasValue &&
        newMedia.Size.HasValue)
    {
        if (oldMedia.Size != newMedia.Size)
        {
            return ProbeDecision.RequireProbe;
        }
    }

    return ProbeDecision.SkipProbe;
}
```

这段逻辑已经包含你确定的：

**URL 改变 + 无 SHA-1 → 必须 ffprobe。**

`oldMedia` 必须来自插件保存的有效历史基线，而不是仅仅从当前 STRM 再读取一次。

对于没有历史基线的首次安装场景，应走专门的初始化逻辑，不能直接调用上述比较函数。

---

# 八、STRM URL 同步模块

这一模块非常重要，不能省略。

Jellyfin 内部使用：

```csharp
item.ShortcutPath
```

保存 STRM 解析出来的远程播放地址。

生成 `MediaSourceInfo` 时会读取这个字段。

源码：

[BaseItem.cs](https://github.com/jellyfin/jellyfin/blob/v12.2/MediaBrowser.Controller/Entities/BaseItem.cs#L1232-L1254)

例如：

```text
原 STRM：
https://openlist.example.com/d/old/movie.mkv

新 STRM：
https://openlist.example.com/d/new/movie.mkv

SHA-1：
相同
```

插件判断：

```text
不需要 ffprobe
```

但是仍必须完成：

```text
item.ShortcutPath
       ↓
更新为新 URL
       ↓
保存 Jellyfin 媒体记录
       ↓
重新获取 MediaSourceInfo
```

否则 JellyfinProxy 可能继续收到旧地址。

## 8.1 推荐处理流程

```text
读取 STRM
    ↓
发现 URL 变化
    ↓
比较 SHA-1
    ↓
SHA-1 相同
    ↓
跳过 ffprobe
    ↓
更新 ShortcutPath
    ↓
通过 Jellyfin 原生接口保存
    ↓
重新生成 MediaSources
    ↓
返回最新 URL
```

Jellyfin 提供 `UpdateToRepositoryAsync()` 等更新入口，但需要验证这一字段的持久化行为。

**开发验收要求：**

URL 更新后，当次播放立即使用新地址；Jellyfin 重启后仍使用新地址；原有媒体流信息不被清除。

如果同步失败，应明确报错或回退原生刷新，不能把旧 URL 当作新媒体源返回。

---

# 九、插件状态数据库

不保存完整 PlaybackInfo。

不保存视频编码、分辨率、音轨信息。

这些继续由 Jellyfin 原生数据库维护。

插件只保存版本和探测状态。

## 9.1 SQLite 表结构

建议：

```sql
CREATE TABLE strm_probe_state (
    item_id TEXT PRIMARY KEY,

    confirmed_url_hash TEXT,

    confirmed_sha1 TEXT,

    confirmed_size INTEGER,

    state TEXT NOT NULL,

    last_probe_at TEXT,

    updated_at TEXT
);
```

其中：

- `confirmed_url_hash`：上次接受的 STRM URL 指纹。
- `confirmed_sha1`：上次接受的内容 SHA-1。
- `confirmed_size`：上次接受的文件大小。
- `state`：探测状态。
- `last_probe_at`：上次成功探测时间。

实际开发时，我建议再拆分**已探测确认的基线**和**最近一次观测到的媒体信息**，避免 SHA-1 暂时缺失时覆盖掉此前有效的哈希。

例如某次生成器没有拿到 SHA-1，不应该因此删除插件保存的最后一个已知有效 SHA-1。

### 9.2 状态分类

```csharp
public enum ProbeState
{
    Assumed,
    Verified,
    PendingProbe,
    ProbeFailed
}
```

| 状态 | 含义 |
|---|---|
| `Assumed` | 首次接管时信任 Jellyfin 原有媒体信息 |
| `Verified` | 已确认媒体探测成功 |
| `PendingProbe` | 媒体变化，等待重新探测 |
| `ProbeFailed` | 新版本探测未成功 |

不能因为读到了新 SHA-1，就立即更新为 `Verified`。

必须确认新媒体源完成了有效探测。

---

# 十、首次安装插件

你可能已经有大量 STRM 入库，并且 Jellyfin 保存了媒体流信息。

不能因为安装插件，就让全部影片重新 ffprobe。

建议默认采用：

**信任已有媒体流，按需建立基线。**

流程：

```text
第一次播放
    ↓
发现插件没有历史记录
    ↓
读取 STRM 的 SHA-1、Size、URL
    ↓
检查 Jellyfin 主媒体流
    ↓
主媒体流存在
    ↓
保存为 Assumed
    ↓
跳过 ffprobe
```

如果不存在必要媒体流：

```text
第一次播放
    ↓
没有 Video / Audio 主流
    ↓
执行 ffprobe
    ↓
确认成功
    ↓
保存为 Verified
```

这样不会在插件首次安装后产生大规模探测。

需要注意：首次建立 `Assumed` 基线并不能证明已有流信息一定属于当前远程文件。若需要更高准确性，可提供首次严格探测模式，但默认关闭。

---

# 十一、ffprobe 成功判断

这是整个插件最需要谨慎实现的部分。

假设：

```text
旧 SHA-1：AAA
新 SHA-1：BBB
```

插件触发探测：

```text
检测到变化
    ↓
执行 Jellyfin 原生刷新
    ↓
OpenList 无法访问
    ↓
ffprobe 失败
```

此时 Jellyfin 数据库可能仍保存旧媒体流。

不能直接写入：

```text
confirmed_sha1 = BBB
state = Verified
```

正确做法：

```text
旧确认基线保留 AAA

待探测版本记录 BBB

state = ProbeFailed
```

下一次允许探测的请求仍然能继续尝试。

## 11.1 成功条件

建议至少满足：

1. 原生探测执行没有发生错误。
2. 能确认此次探测实际取得了新的媒体信息。
3. 新媒体信息已经保存。
4. 保存后的媒体流包含必要主流。
5. STRM 在探测期间没有再次发生变化。

特别是第五项。

如果执行 ffprobe 时，STRM 生成器又更新了文件，那么这次探测结果可能已经不对应最新版本。

因此可以采用：

```text
读取 Manifest A
        ↓
执行 ffprobe
        ↓
读取 Manifest B
        ↓
A == B？
        │
   ┌────┴────┐
   │         │
  是         否
   │         │
   ▼         ▼
确认状态   保留待验证状态
```

不过 `item.RefreshMetadata()` 返回的 `ItemUpdateType` 并不是 ffprobe 成功的直接证明。

所以正式开发时需要找到可靠的探测结果信号。

**这项验证应该放在最早的开发阶段，而不是插件全部完成后才测试。**

---

# 十二、并发处理

假设三个客户端同时播放一部更新后的 STRM。

如果没有并发控制：

```text
客户端 A → ffprobe
客户端 B → ffprobe
客户端 C → ffprobe
```

会浪费时间和资源。

建议使用 `ProbeCoordinator`：

```text
客户端 A ─┐
客户端 B ─┼──── ItemId
客户端 C ─┘
                 │
                 ▼
           检查进行中任务
                 │
                 ▼
          共享同一次探测
                 │
                 ▼
             探测完成
                 │
                 ▼
          重新检查版本状态
                 │
                 ▼
          各客户端继续播放
```

推荐使用每个媒体项目独立的异步协调机制。

不同 STRM 不需要互相等待。

但如果 Jellyfin 存在多版本影片，还应将媒体源身份纳入协调键，避免将不同版本当作同一个媒体文件。

---

# 十三、插件与 JellyfinProxy 的关系

这两个项目保持独立。

最终流程：

```text
STRM 生成器
    │
    ▼
带 SHA-1 / Size 的 STRM
    │
    ▼
Jellyfin
    │
    ▼
StrmProbeOptimizer
    │
    ├── 没变化 → 跳过 ffprobe
    │
    └── 有变化 → ffprobe
    │
    ▼
Jellyfin PlaybackInfo
    │
    ▼
JellyfinProxy
    │
    ├── 修改 MediaSources
    │
    ├── 更新 MediaSourceId → URL 映射
    │
    └── 返回客户端
    │
    ▼
播放器请求视频
    │
    ▼
JellyfinProxy 302
    │
    ▼
OpenList
```

## 不需要再使用完整 PlaybackInfo JSON 缓存

当前 JellyfinProxy 中的完整 PlaybackInfo 缓存，本质上是在减少访问 Jellyfin 时可能触发的重复探测。

当插件能正确避免这种探测，就可以逐步关闭该缓存。

但必须保留：

**MediaSourceId → URL 映射缓存。**

它仍然负责 302 重定向。

建议在插件实测稳定后，再关闭完整 PlaybackInfo 缓存，而不是同时修改两个系统。

---

# 十四、插件配置

第一版建议提供以下配置。

| 配置项 | 默认值 |
|---|---|
| 启用 STRM 优化 | 开启 |
| 使用 STRM SHA-1 | 开启 |
| SHA-1 不可比较时使用 Size | 开启 |
| URL 变化且无法比较 SHA-1 时探测 | 强制开启 |
| SHA-1 相同时忽略 Size 变化 | 强制开启 |
| 忽略 Modified 变化 | 强制开启 |
| 缺少主媒体流时探测 | 开启 |
| 首次信任已有媒体流 | 开启 |
| 定期无条件 ffprobe | 关闭 |
| URL 变化、SHA-1 相同时只更新路径 | 开启 |
| 无版本标记的旧 STRM | Jellyfin 原生处理 |
| 输出详细探测日志 | 关闭 |

这里建议将关键判断规则写死为插件业务规范，而不是全部暴露成可随意修改的开关。

这样更方便维护和测试。

---

# 十五、兼容性与异常处理

## 15.1 Jellyfin 版本

建议先确定一个目标 Jellyfin 版本，构建独立兼容包。

目前已核对过 Jellyfin 10.11.8 和 v12.2 相关接口，但不能假设一份插件二进制同时兼容所有版本。

尤其是核心 DI 服务包装，版本升级后可能需要调整。

## 15.2 手动强制刷新

Jellyfin 自带的手动元数据刷新不能被插件禁止。

如果用户明确要求重新探测，应允许原生流程执行，并在能够确认成功时同步插件状态。

对于插件之外执行的媒体流刷新，也需要设计状态协调：不能仅凭 Jellyfin 发出“媒体已更新”事件就把当前版本标记为 `Verified`。

## 15.3 STRM 解析失败

如果 STRM 不存在、内容为空、URL 无效或标记不合法：

- 不覆盖原有可信状态。
- 不把非法 URL 写入 `ShortcutPath`。
- 回退原生处理或返回明确错误。
- 日志记录原因，但不泄露签名 URL。

## 15.4 SQLite 数据异常

不能因为插件数据库错误让 Jellyfin 整体无法播放。

运行时应停止优化，尽可能退回 Jellyfin 原生逻辑。

核心服务替换失败则应在启动阶段明确报错，不能声称一定可以安全自动回退。

---

# 十六、完整测试矩阵

这是正式开发时建议必须通过的测试。

| 编号 | 测试场景 | 预期结果 |
|---|---|---|
| T01 | 首次播放，没有媒体流 | ffprobe |
| T02 | 已有媒体流，首次安装插件 | Assumed，不 ffprobe |
| T03 | URL 不变，SHA-1 相同 | 不 ffprobe |
| T04 | URL 不变，SHA-1 不同 | ffprobe |
| T05 | URL 不变，SHA-1 相同，Size 不同 | 不 ffprobe |
| T06 | URL 不变，无 SHA-1，Size 相同 | 不 ffprobe |
| T07 | URL 不变，无 SHA-1，Size 不同 | ffprobe |
| T08 | URL 改变，SHA-1 相同 | 仅更新 URL |
| T09 | URL 改变，SHA-1 不同 | ffprobe |
| **T10** | **URL 改变，无 SHA-1，Size 相同** | **ffprobe** |
| **T11** | **URL 改变，无 SHA-1，Size 不同** | **ffprobe** |
| T12 | URL 改变，仅一侧有 SHA-1 | ffprobe |
| T13 | 只有 Modified 改变 | 不 ffprobe |
| T14 | 删除后重新生成相同 STRM | 只要媒体库记录及状态保留，就不 ffprobe |
| T15 | SHA-1 不变，生成程序重新写入 STRM | 不 ffprobe |
| T16 | URL 不变，视频替换且 SHA-1 改变 | ffprobe |
| T17 | ffprobe 失败 | 不提交新确认版本 |
| T18 | STRM 在探测过程中再次改变 | 不错误确认旧结果 |
| T19 | Jellyfin 重启 | 状态正确恢复 |
| T20 | 多客户端并发播放 | 不重复探测 |
| T21 | 手动强制刷新 | 允许原生刷新 |
| T22 | `ShortcutPath` 改变后重启 | 新 URL 保持有效 |
| T23 | 未安装插件 | Jellyfin 原生行为 |
| T24 | 禁用插件 | Jellyfin 原生行为 |
| T25 | 多版本影片 | 正确区分每个版本 |
| T26 | 旧 STRM 无版本标记 | 按兼容策略处理 |
| T27 | SHA-1 暂时缺失，随后恢复 | 不错误丢失历史有效哈希 |
| T28 | `allowMediaProbe=false` | 不擅自启动探测 |

其中 T10 是你最新强调的规则，必须作为单独的自动化测试。

---

# 十七、开发实施顺序

建议按四个阶段推进。

## P0：Jellyfin 核心接入验证

先做最小原型：

- 创建插件项目。
- 注册 `IMediaSourceManager` 包装器。
- 保留原生服务实例。
- 仅对 STRM 修改探测判断。
- 验证可以跳过重复探测。
- 验证可以主动执行原生远程探测。
- 验证能否确认探测真正成功。

**验收条件：Jellyfin 能正常启动，已入库 STRM 的第二次播放不再触发重复 ffprobe。**

同时确保普通媒体播放不受影响。

如果核心服务包装不稳定，就应该在这一阶段调整实现方式，而不是继续开发全部功能。

## P1：修改 STRM 生成程序

实现：

- OpenList SHA-1 提取。
- 文件 Size 提取。
- 新 STRM 注释格式。
- 内容相同时不写入。
- 原子替换文件。

**验收条件：生成程序能稳定地产生版本标记，且视频文件版本变化才导致相应标记变化。**

## P2：实现完整插件判断

开发：

- STRM 解析器。
- 变化判断引擎。
- SQLite 状态持久化。
- 并发协调。
- ffprobe 成功确认。
- URL 变化后的路径同步。

**验收条件：T01～T28 核心测试全部通过。**

## P3：JellyfinProxy 联动测试

测试：

```text
生成 STRM
    ↓
Jellyfin 入库
    ↓
第一次播放
    ↓
第二次播放
    ↓
修改远程视频
    ↓
重新生成 STRM
    ↓
再次播放
    ↓
检查 PlaybackInfo
    ↓
检查 JellyfinProxy 302
```

重点观察：

- PlaybackInfo 耗时。
- 实际 ffprobe 调用次数。
- OpenList 视频地址是否正确。
- Jellyfin 数据库媒体流是否同步更新。
- Jellyfin 重启后行为是否正确。

通过这些测试后，再关闭 JellyfinProxy 的完整 JSON 缓存。

---

# 十八、最终开发规范

建议将以下内容固定为 V3.0 的开发基准。

| 项目 | 最终方案 |
|---|---|
| 项目名称 | Jellyfin.Plugin.StrmProbeOptimizer |
| 插件语言 | C# |
| 插件平台 | Jellyfin Server |
| STRM 生成器 | 可修改，负责写入版本信息 |
| 远程媒体来源 | OpenList |
| 版本信息 | SHA-1、Size |
| 版本信息存放位置 | STRM 注释 |
| URL 判断 | 比较有效播放 URL |
| SHA-1 判断优先级 | 最高 |
| SHA-1 相同 | 不 ffprobe |
| SHA-1 不同 | ffprobe |
| URL 不变、无 SHA-1、Size 相同 | 不 ffprobe |
| URL 不变、无 SHA-1、Size 不同 | ffprobe |
| **URL 改变、无可比较 SHA-1** | **必须 ffprobe** |
| URL 改变、SHA-1 相同 | 更新 URL，不 ffprobe |
| Modified 变化 | 忽略 |
| 缺少必要主媒体流 | ffprobe |
| 首次安装 | 默认信任已有媒体流 |
| 定期强制探测 | 不启用 |
| 插件请求 OpenList API | 不需要 |
| 插件持久化 | SQLite |
| ffprobe 结果存储 | Jellyfin 原生数据库 |
| 完整 PlaybackInfo 缓存 | 不需要 |
| JellyfinProxy 302 | 保持现有逻辑 |

---

## 十九、建议先解决的三个技术难点

虽然业务规则已经完整，但还有三个需要通过真实代码验证的技术问题：

**1. `IMediaSourceManager` 包装器是否稳定。**  
它能否在 Jellyfin 启动阶段正确替换核心服务，同时完整保留其他媒体源功能。

**2. SHA-1 相同而 URL 变化时，能否安全地只更新 `ShortcutPath`。**  
不能为了省一次 ffprobe，导致 JellyfinProxy 获取错误的播放地址。

**3. 如何证明本次 ffprobe 真正成功。**  
不能仅凭原生刷新方法返回，就直接把新 SHA-1 标记为已经成功探测。

这三项是 P0 阶段的技术验证重点。

---

## 二十、最终架构

```text
                   OpenList
                      │
                      ▼
                STRM 生成程序
                      │
             提取 SHA-1 / Size
                      │
                      ▼
              生成版本化 STRM
                      │
                      ▼
                Jellyfin 媒体库
                      │
                      ▼
                用户请求播放
                      │
                      ▼
             StrmProbeOptimizer
                      │
             ┌────────┴────────┐
             │                 │
             ▼                 ▼
         STRM 信息        Jellyfin 媒体流
             │                 │
             └────────┬────────┘
                      ▼
                 比较版本
                      │
             ┌────────┴────────┐
             │                 │
          不需要探测        需要探测
             │                 │
             ▼                 ▼
        复用媒体流         原生 ffprobe
             │                 │
             │                 ▼
             │             保存媒体流
             │                 │
             │                 ▼
             │           确认探测成功
             │                 │
             │                 ▼
             │           更新插件状态
             │                 │
             └────────┬────────┘
                      ▼
              同步必要的播放 URL
                      │
                      ▼
             Jellyfin PlaybackInfo
                      │
                      ▼
                JellyfinProxy
                      │
                      ▼
                  客户端播放
```

### 最终建议

**采用 V3.0：STRM 内嵌 SHA-1/Size + 插件比较 URL 和媒体版本 + 按需调用 Jellyfin 原生 ffprobe。**

这个方案把 OpenList 元数据获取放在 STRM 生成阶段，把播放阶段需要做的工作缩减为本地文件读取、状态查询和简单比较。

对于大量 STRM，正常重复播放无需调用 OpenList，也无需执行 ffprobe。

同时，你强调的 **URL 改变但没有 SHA-1 时必须重新探测** 已经纳入核心判断逻辑和自动化测试。

**目前这是可用于正式开发的 V3.0 设计方案，不代表插件已经实现或通过实机验证。建议先按 P0 完成核心接入和探测成功确认，再进入后续开发。**