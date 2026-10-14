# Jellyfin STRM Probe Optimizer V4.3 开发方案

**基于 V4.2，仅调整批量扫描方式，其他功能不变。**

保持插件简单，不开发独立任务调度系统，也不维护额外的 ffprobe 成功、失败状态机。

## 一、核心功能

插件提供两种工作方式：

**1. 播放时自动检查**

用户点击播放时，插件读取 STRM 的 URL、SHA-1、Size，并与历史指纹比较。

没有变化就复用 Jellyfin 已保存的媒体流；发生变化才执行原生 ffprobe。

**2. 批量检查任务（新增）**

在 Jellyfin 的「控制台 → 计划任务」中增加：

`STRM 媒体信息检查`

支持 Jellyfin 原生的：

- 手动运行、停止任务。
- 设置每天、每周等执行时间。
- 查看运行进度及执行结果。
- 由 Jellyfin 自动管理计划任务。

无需单独开发手动运行按钮和定时调度界面。

已核对 Jellyfin v12.2 源码，插件可以通过 `IScheduledTask` 接入这套机制。

参考：[Jellyfin IScheduledTask.cs](https://github.com/jellyfin/jellyfin/blob/v12.2/MediaBrowser.Model/Tasks/IScheduledTask.cs)

---

## 二、ffprobe 判断规则

继承 V4.1，完全不变。

| 条件 | 处理 |
|---|---|
| 缺少必要主媒体流 | ffprobe |
| **URL 变化** | **ffprobe** |
| URL 不变，SHA-1 相同 | 跳过 |
| URL 不变，SHA-1 不同 | ffprobe |
| URL 不变，无可比较 SHA-1，Size 相同 | 跳过 |
| URL 不变，无可比较 SHA-1，Size 不同 | ffprobe |
| URL 不变，SHA-1、Size 都无法比较 | 默认跳过 |
| 仅 Modified 变化 | 跳过 |

播放检查与批量任务**共用同一套判断逻辑**。

---

## 三、批量任务执行流程

```text
Jellyfin 计划任务
        │
        ▼
手动运行 / 定时触发
        │
        ▼
获取所选库候选 ID
        │
        ▼
分批读取当前媒体项目
        │
        ▼
检查 Jellyfin 媒体流
        │
        ▼
比较 URL、SHA-1、Size
        │
   ┌────┴────┐
   │         │
 无变化     有变化
   │         │
   ▼         ▼
  跳过     按需申请探测
             │
             ▼
        并发数量控制
             │
             ▼
       Jellyfin 原生 ffprobe
             │
             ▼
       Jellyfin 保存媒体信息
             │
             ▼
       确认后提交历史指纹
             │
             ▼
         更新任务进度
```

批量任务采用**增量检查模式**。

即使媒体库有 10 万个 STRM，也不会全部重新 ffprobe，只处理需要探测的项目。

首次运行时，默认信任 Jellyfin 已保存的媒体流，避免对整个媒体库进行重新探测。

扫描先获取所选媒体库的候选 ID，去重后固定本轮集合，再分批读取当前媒体对象；每批结算后处理下一批，不一次性加载完整媒体对象。ID 集合随候选数增长，读取时重核范围，新增项目留下一轮。

---

## 四、并发控制

在插件配置中增加：

**最大 ffprobe 并发数**

默认：`2`

允许设置：`1～8`

例如设置为 3：

```text
          待探测 STRM
                │
                ▼
           并发控制器
                │
       ┌────────┼────────┐
       │        │        │
       ▼        ▼        ▼
    ffprobe1 ffprobe2 ffprobe3
       │        │        │
       └────────┼────────┘
                │
                ▼
            继续下一批
```

采用 `SemaphoreSlim` 或有界任务队列实现。

**播放自动探测和批量任务共用 `ProbeCoordinator`。**

对于同一部影片，不重复启动相同探测任务。

并发限制只覆盖插件主动发起的探测，不会限制 Jellyfin 其他独立任务或其他插件发起的 ffprobe。

---

## 五、与 Jellyfin 计划任务配合

新增：

```csharp
public class StrmProbeScheduledTask
    : IScheduledTask, IConfigurableScheduledTask
```

任务名称：

`STRM 媒体信息检查`

任务默认不设置自动执行时间，由管理员自行在 Jellyfin 中配置。

例如：

```text
01:00  STRM 生成器完成更新
02:00  Jellyfin 扫描媒体库
03:00  STRM 媒体信息检查
```

这样可以先入库，再检测媒体变化。

但独立时间计划不能严格保证前一个任务已经完成。

如果后续需要**必须在 Jellyfin 媒体库扫描完成后执行**，可以增加 `ILibraryPostScanTask` 接口，直接挂接 Jellyfin 的扫描后任务机制。

该接口也已在 v12.2 中确认存在。

建议第一版先使用 `IScheduledTask`，不增加扫描后自动触发，以减少复杂度。

---

## 六、精简后的插件结构

```text
Jellyfin.Plugin.StrmProbeOptimizer/
│
├── Plugin.cs
├── PluginConfiguration.cs
├── ServiceRegistrator.cs
│
├── Services/
│   ├── StrmManifestReader.cs
│   ├── ProbeDecisionService.cs
│   ├── ProbeCoordinator.cs
│   └── NativeProbeExecutor.cs
│
├── Tasks/
│   └── StrmProbeScheduledTask.cs
│
├── Persistence/
│   └── StrmFingerprintRepository.cs
│
└── Configuration/
    └── ConfigurationPage.html
```

取消独立的：

```text
ProbeState
ProbeFailed
PendingProbe
ShortcutPathSynchronizer
```

插件不保存完整媒体信息，仍由 Jellyfin 原生数据库负责。

---

## 七、插件配置

| 配置项 | 默认值 |
|---|---|
| 启用插件 | 开启 |
| 播放时自动检查 | 开启 |
| URL 变化自动 ffprobe | 开启 |
| SHA-1 / Size 变化检测 | 开启 |
| 最大 ffprobe 并发数 | **2** |
| 批量任务媒体库范围 | 全部媒体库 |
| 批量任务处理方式 | 仅处理需要探测的媒体 |
| 首次信任已有媒体信息 | 开启 |
| 定期执行时间 | Jellyfin 计划任务配置 |
| 详细日志 | 关闭 |

计划任务可以支持取消，并通过 Jellyfin 原生进度接口报告已检查数量和处理进度。

任务完成后，日志统计：

```text
检查 STRM：10000
跳过探测：9850
需要探测：150
成功探测：148
未能完成：2
```

这里的成功数量必须来自可靠的原生探测结果，不能只通过刷新方法返回判断。

---

## 八、历史指纹管理

仍然只保存最小历史信息：

```sql
CREATE TABLE strm_fingerprint (
    item_id TEXT NOT NULL,
    source_key TEXT NOT NULL,
    url_hash TEXT NOT NULL,
    sha1 TEXT,
    file_size INTEGER,
    PRIMARY KEY (item_id, source_key)
);
```

不增加独立的成功、失败状态。

**但保留 V4.1 尚未解决的技术要求：新指纹只能在确认本次 Jellyfin 原生探测结果有效且已保存后提交。**

目前不能仅凭 `RefreshMetadata()` 返回或旧媒体流仍然存在来确认成功。

这个问题必须在 P0 阶段通过 Jellyfin 实际探测链路验证。无法确认时，不更新历史指纹，下一次仍将检测到变化。

批量任务和播放请求使用完全相同的指纹提交机制。

---

## 九、完整运行架构

```text
                  OpenList
                     │
                     ▼
                STRM 生成器
                     │
                     ▼
                Jellyfin 媒体库
                     │
          ┌──────────┴──────────┐
          │                     │
          ▼                     ▼
      客户端播放           Jellyfin 计划任务
          │                     │
          │              手动 / 定时运行
          │                     │
          ▼                     ▼
     单个 STRM 检查         批量 STRM 检查
          │                     │
          └──────────┬──────────┘
                     │
                     ▼
             ProbeDecisionService
                     │
                     ▼
               是否需要 ffprobe
                     │
              ┌──────┴──────┐
              │             │
              否            是
              │             │
              ▼             ▼
          复用媒体流     ProbeCoordinator
              │             │
              │             ▼
              │        最大并发数控制
              │             │
              │             ▼
              │       Jellyfin 原生探测
              │             │
              │             ▼
              │       Jellyfin 保存媒体流
              │             │
              └──────┬──────┘
                     │
                     ▼
               Jellyfin 原生数据
```

---

## 十、开发顺序

**P0：核心验证**

验证 Jellyfin 媒体源拦截、原生 ffprobe 调用以及可靠的指纹提交机制。

**P1：核心插件**

完成 STRM 解析、变化判断、历史指纹比较和播放时按需探测。

**P2：批量任务**

增加 `IScheduledTask`、Jellyfin 手动运行、定时执行、并发控制、取消任务及进度报告。

**P3：集成测试**

验证大规模 STRM、并发探测、Jellyfin 定时任务、媒体库扫描以及 JellyfinProxy 播放流程。

---

## V4.3 最终方案

采用：

**播放自动检查 + Jellyfin 原生计划任务 + 可配置最大并发 + 按需 ffprobe。**

相比 V4.1，仅新增一个计划任务模块，并在现有 `ProbeCoordinator` 中加入并发控制。

不开发额外的调度系统，不维护自己的探测状态机，不重复保存 Jellyfin 媒体信息。

**建议将 V4.3 作为新的开发基准。**