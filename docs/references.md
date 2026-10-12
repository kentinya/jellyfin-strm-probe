# 参考来源

读取日期：2026-10-12。引用外部流程并针对本项目重新编写；没有复制 mediaflow 的媒体整理实现、Storage／Recognition 架构或“禁止 FFprobe”产品规则。

## 原始方案

文件：[Jellyfin STRM Probe Optimizer 完整开发方案 V3.0.md](<../Jellyfin STRM Probe Optimizer 完整开发方案 V3.0.md>)。

原文件 SHA-256：`d236cab6b3992636b524f30bbe49a91adb9ef5d6b7010ed5695cae7d65f228ae`。初始化前校验此值，原文保持不变。生成程序排除项由 [scope.md](scope.md) 明确记录。

## mediaflow 开发流程

仓库：[kentinya/mediaflow](https://github.com/kentinya/mediaflow)。本次读取时 main 提交：`df4391bd2ff351cbcfc34d24f193aff5abb59dbc`。

| 来源 | 读取文件的 Git blob SHA | 本项目适配 |
|---|---|---|
| [development-workflow.md](https://github.com/kentinya/mediaflow/blob/df4391bd2ff351cbcfc34d24f193aff5abb59dbc/docs/development-workflow.md) | `b9e2b0a94fad4afce61efdd94ad175162c02a7e5` | Slice／Task、A／B／Developer、T0～T4、Git 激活、审查和停止规则 |
| [Task/TEMPLATE.md](https://github.com/kentinya/mediaflow/blob/df4391bd2ff351cbcfc34d24f193aff5abb59dbc/Task/TEMPLATE.md) | `c5af426b93031b30ceff8647ffb2371dadc34f18` | Task 目标、范围、测试、完成报告与审查结构 |
| [check_governance.py](https://github.com/kentinya/mediaflow/blob/df4391bd2ff351cbcfc34d24f193aff5abb59dbc/scripts/check_governance.py) | `548c7a89020a567af4936ec1215e20871d05589c` | 本项目独立实现只读合同检查，增加未初始化的规划检查 |

还读取了 AGENTS、CLAUDE、SLICE、TASK 和 Roadmap，了解文档职责与当前合同格式。本项目没有继承这些文件中的产品规则和历史验收结果，没有配置该仓库为本项目远程。

## Jellyfin 源码定位

| 来源 | 目的 |
|---|---|
| [v10.11.8 标签](https://github.com/jellyfin/jellyfin/tree/v10.11.8) | 对应提交 `2c62d40f0d13926874eef9118a95be0dcee4e659`，候选兼容版本 |
| [v10.11.8 global.json](https://github.com/jellyfin/jellyfin/blob/2c62d40f0d13926874eef9118a95be0dcee4e659/global.json) | 已读取 SDK 9.0.0／latestMinor；不是插件已构建证据 |
| [v12.2 标签提交](https://github.com/jellyfin/jellyfin/commit/ca0f16eb7c195f720a1493ed469a27c4657db0c6) | 确认原方案标签存在，仍需目标服务器验证 |
| [MediaSourceManager.cs](https://github.com/jellyfin/jellyfin/blob/v12.2/Emby.Server.Implementations/Library/MediaSourceManager.cs) | 原方案提出的 GetPlaybackMediaSources 接入位置，Task 1.1 核实 |
| [ProbeProvider.cs](https://github.com/jellyfin/jellyfin/blob/v12.2/MediaBrowser.Providers/MediaInfo/ProbeProvider.cs) | 原方案提出的 STRM 注释／URL 读取位置，Task 1.1 核实 |
| [BaseItem.cs](https://github.com/jellyfin/jellyfin/blob/v12.2/MediaBrowser.Controller/Entities/BaseItem.cs) | 原方案提出的 ShortcutPath 和持久化位置，Task 1.1 核实 |

后三项是待核实定位，当前没有据此宣布接口或二进制已兼容。不读取 OpenList API 或生成程序实现，因为本次范围已经排除。
