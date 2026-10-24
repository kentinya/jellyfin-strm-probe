# 单版本安装、配置与恢复说明

本页说明首版固定组合的本地安装包、配置、备份／恢复、禁用／移除／重装步骤与已验证支持范围。它是 [Slice 4](progress.md#slice-4-closed) RO-1 的交付材料；大库与扫描分别属于 RO-2／RO-3，最终接受范围见 [A Final Review](progress.md#slice-4-closed)，不在本页复制状态。按用户授权不验证 JellyfinProxy，代理未验证、不承诺兼容；原始证据见 [Closure Packet](progress.md#slice-4-closed)。

后续视频结果匹配修正及同一正式ZIP的播放／安装／扫描／大库回归接受范围见[Slice 5最终审查](progress.md#slice-5-closed)；包的来源、摘要和证据复用以该合同为准，安装与恢复步骤不变。

## 已验证支持范围

| 维度 | 首版实测范围 |
|---|---|
| Jellyfin | `12.2.0`（官方镜像 `12.2`，digest 见 [环境交接](development-environment.md)） |
| 操作系统／架构 | Linux x64 |
| 目标框架 | `net10.0`；SDK `10.0.401` |
| 插件 ABI | `targetAbi` `12.2.0.0`；GUID `b061643e-d17d-4c6e-8ba2-6b57e286bd20` |
| 媒体封装 | MP4（H.264／AAC）与 MKV（H.264／AAC） |
| 客户端 | Jellyfin 原生 Web 客户端实际播放 |
| 代理 | JellyfinProxy 未验证；按用户授权不执行，不属于当前交付兼容承诺 |

固定组合之外的 Jellyfin 版本、操作系统、CPU 架构、其他封装／编解码、第三方客户端与转码模式不在首版支持声明内。安装包不包含 Jellyfin 核心运行库、另一套 FFmpeg 或非 Linux x64 的 native 依赖。

## 取得安装包

首版从 [GitHub Release v0.1.0](https://github.com/kentinya/jellyfin-strm-probe/releases/tag/v0.1.0) 下载插件 ZIP、来源清单、`.zip.sha256` 和 `SHA256SUMS.txt`。附件与已验收包保持一致；下载全部附件后在同一目录执行 `sha256sum -c SHA256SUMS.txt`。Jellyfin 12.3 尚未实机验证。

开发者也可本地打包；从其他提交或普通构建路径生成的包不自动等同于 Release 附件，来源及路径复现规则见[发布流程](release-process.md)。打包入口从固定 Release 输出与已锁依赖生成归档：

```bash
bash scripts/dotnet-local restore Jellyfin.Plugin.StrmProbeOptimizer.sln --locked-mode
bash scripts/dotnet-local build Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore
python3 scripts/package_plugin.py --configuration Release --runtime linux-x64 --output-dir artifacts/releases
```

产物（默认在 `artifacts/releases/`）：

- `Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip`：归档；
- `Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.manifest.json`：来源、SDK、运行时、依赖、许可、每文件摘要、构建命令与输入摘要及归档 SHA-256；
- `Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip.sha256`：归档校验值。

打包要求工作区无未提交的受跟踪改动；`--source-revision` 必须等于当前 HEAD 且为真实可达提交，该 SHA 通过 `-p:SourceRevisionId` 写入程序集构建标识，并在打包时核对。清单同时记录锁文件与构建输入摘要，可用于复建。

校验归档（部署前，必须在归档所在目录执行 `sha256sum -c`，因为清单只记录文件名）：

```bash
python3 scripts/package_plugin.py --verify artifacts/releases/Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip
(cd artifacts/releases && sha256sum -c Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip.sha256)
```

`--verify` 会自动读取归档旁的同名 `.manifest.json`，并比对归档 SHA-256、每个负载文件摘要、依赖完整性、程序集版本与元数据；清单缺失或不匹配即拒绝。包验收部署同样默认读取该清单，不会用重新计算的摘要自证。

归档内含一个顶层插件目录 `Jellyfin.Plugin.StrmProbeOptimizer_0.1.0.0/`，其中有插件程序集、依赖清单、托管与 Linux x64 native SQLite 负载、`meta.json` 和 `THIRD-PARTY-NOTICES.txt`。它不含源码、测试、SDK、凭据、媒体库数据或运行状态。拒绝损坏归档、缺失 native、GUID／ABI 不符、越界路径与符号链接；拒绝时不会覆盖已有有效安装。

## 安装

1. 停止目标 Jellyfin（或在其插件目录不被写入时操作）。
2. 将归档解出的顶层插件目录整体复制到 Jellyfin 的插件目录，例如容器内 `/config/plugins/`：

   ```bash
   unzip -q Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip -d /path/to/jellyfin/config/plugins/
   ```

3. 启动 Jellyfin。启动日志应出现插件初始化与「Loaded plugin: STRM Probe Optimizer 0.1.0.0」。
4. 打开「控制台 → 插件」，确认状态为 Active。

干净实例只使用归档解出的文件即可；不需要源码树、开发机 SDK、NuGet 缓存或额外补丁 DLL。

## 配置

在「控制台 → 插件 → STRM Probe Optimizer → 设置」打开配置页，五项可编辑：

| 项 | 默认 | 生效时机 |
|---|---|---|
| 启用插件 | 开 | 保存后的下一请求 |
| 播放自动检查 | 开 | 保存后的下一请求 |
| 主动探测并发 | 2（1～8） | 下次 Jellyfin 启动 |
| 批量媒体库范围 | 全部 | 下一轮任务 |
| 详细日志 | 关 | 保存后的下一请求 |

URL 变化必探测、SHA-1／Size 决策、Modified 忽略与权限边界是固定规则，不以开关形式提供。页面在加载失败、未确认保存、服务器拒绝与范围失效时给出明确反馈；非法并发（0、9、非整数等）在提交前被拒绝。

批量检查由 Jellyfin 原生计划任务「控制台 → 计划任务 → STRM 媒体信息检查」运行，默认没有触发时间；手动运行、停止与定时由 Jellyfin 管理，插件页不提供独立运行按钮或调度器。

## 备份与恢复

- 配置：`config/plugins/configurations/Jellyfin.Plugin.StrmProbeOptimizer.xml`。
- 历史指纹：`config/data/plugins/b061643ed17d4c6e8ba26b57e286bd20/` 下的 `strm-fingerprints.db`（实际目录名以 GUID 十六进制为准）。

备份即在 Jellyfin 停止时复制上述文件；恢复即放回同一路径后启动。插件不会自动删除或重建状态库；无 schema 变化时不需要迁移步骤。恢复失败时如实报告，不伪装成功。包验收入口会在停止服务器后实际执行备份、通过正常 API 改动配置、再停止、恢复、重启并读回核对（`scripts/run_isolated_package_integration.py --scenario upgrade`）。

包验收入口每轮使用 `artifacts/package-env/runs/` 下新创建、带本轮归属标记的独立工作区，不复用或修改既有目录。`--workspace` 只能指定尚不存在或空的目录；任何已有非空目录（包括上一轮 `--keep-workspace` 留存、仍带旧标记的目录）都会在任何写入、停止或删除前被拒绝，旧数据保持原样。清理同时核对本轮实际创建事实与标记内容，只删除确认属于本轮的工作区；运行前拒绝非本轮数据，结束后核对配置、指纹、媒体、STRM、原生任务触发器与库条目的前后状态，任何已有输入被改动都会使整轮 FAIL。默认清理，`--keep-workspace` 可保留供检查（留存目录不授权下一轮修改或删除）。

## 禁用、移除与重装

- 禁用：在「控制台 → 插件」停用插件并重启；播放与批量委托 Jellyfin 原生，不发起插件探测。
- 移除：停用后删除插件目录并重启；原生播放继续可用。
- 重装：重新放入归档解出的插件目录并重启，插件恢复 Active；已有配置与指纹若保留会被继续使用，未完成的变化在下次检查时重新比较。

上述步骤已由 `scripts/run_isolated_package_integration.py --scenario recovery` 在专用隔离实例验证（禁用／移除后原生播放、重装后重新检查）。

## 故障与恢复

- 运行时 SQLite 异常：停止优化并尽可能委托原生播放；批量报告不可用。修复状态库并重启后重新检查。
- 启动核心注册失败：明确报告；不承诺一定自动回退。
- 媒体不可达、探测失败或探测期间 STRM 变化：保留旧可信指纹，修复后下次重新比较。

## 交付与未验证边界

RO-2 大库／RO-3 扫描的证据与本地 ZIP 安装证据分别接受，见 [Closure Packet](progress.md#slice-4-closed) 与 [A 最终决定](progress.md#slice-4-closed)，不由本页安装步骤代替。按 2026-10-24 用户授权，首版另通过 [GitHub Release](https://github.com/kentinya/jellyfin-strm-probe/releases/tag/v0.1.0) 分发同一已验收安装包；发布流程见[发布说明](release-process.md)，插件仓库自动上架未执行。JellyfinProxy 专属验收按用户授权撤出，历史 NOT RUN、不宣称兼容；真实 OpenList 专有行为及其他未测组合仍未验证。
