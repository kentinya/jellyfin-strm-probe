# 单版本安装、配置与恢复说明

本页说明首版固定组合的本地安装包、配置、备份／恢复、禁用／移除／重装步骤与已验证支持范围。它是 [Slice 4](../SLICE.md) RO-1 的交付材料；真实十万库、完整扫描压力与实际 JellyfinProxy 联调属于 RO-2／RO-3／RO-4，仍为 TARGET／NOT RUN。

## 已验证支持范围

| 维度 | 首版实测范围 |
|---|---|
| Jellyfin | `12.2.0`（官方镜像 `12.2`，digest 见 [环境交接](development-environment.md)） |
| 操作系统／架构 | Linux x64 |
| 目标框架 | `net10.0`；SDK `10.0.401` |
| 插件 ABI | `targetAbi` `12.2.0.0`；GUID `b061643e-d17d-4c6e-8ba2-6b57e286bd20` |
| 媒体封装 | MP4（H.264／AAC）与 MKV（H.264／AAC） |
| 客户端 | Jellyfin 原生 Web 客户端实际播放 |
| 代理 | 未包含在本安装包验收；实际 JellyfinProxy 见 RO-4（NOT RUN） |

固定组合之外的 Jellyfin 版本、操作系统、CPU 架构、其他封装／编解码、第三方客户端与转码模式不在首版支持声明内。安装包不包含 Jellyfin 核心运行库、另一套 FFmpeg 或非 Linux x64 的 native 依赖。

## 取得安装包

打包入口从固定 Release 输出与已锁依赖生成归档：

```bash
bash scripts/dotnet-local restore Jellyfin.Plugin.StrmProbeOptimizer.sln --locked-mode
bash scripts/dotnet-local build Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore
python3 scripts/package_plugin.py --configuration Release --runtime linux-x64 --output-dir artifacts/releases
```

产物（默认在 `artifacts/releases/`）：

- `Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip`：归档；
- `Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.manifest.json`：来源、SDK、运行时、依赖、许可、每文件摘要与归档 SHA-256；
- `Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip.sha256`：归档校验值。

校验归档（部署前）：

```bash
python3 scripts/package_plugin.py --verify artifacts/releases/Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip
sha256sum -c artifacts/releases/Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip.sha256
```

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

备份即在 Jellyfin 停止时复制上述文件；恢复即放回同一路径后启动。插件不会自动删除或重建状态库；无 schema 变化时不需要迁移步骤。恢复失败时如实报告，不伪装成功。

## 禁用、移除与重装

- 禁用：在「控制台 → 插件」停用插件并重启；播放与批量委托 Jellyfin 原生，不发起插件探测。
- 移除：停用后删除插件目录并重启；原生播放继续可用。
- 重装：重新放入归档解出的插件目录并重启，插件恢复 Active；已有配置与指纹若保留会被继续使用，未完成的变化在下次检查时重新比较。

上述步骤已由 `scripts/run_isolated_package_integration.py --scenario recovery` 在专用隔离实例验证（禁用／移除后原生播放、重装后重新检查）。

## 故障与恢复

- 运行时 SQLite 异常：停止优化并尽可能委托原生播放；批量报告不可用。修复状态库并重启后重新检查。
- 启动核心注册失败：明确报告；不承诺一定自动回退。
- 媒体不可达、探测失败或探测期间 STRM 变化：保留旧可信指纹，修复后下次重新比较。

## 未交付范围

真实十万原生库成本（RO-2）、完整库扫描与播放／批量重叠（RO-3）、实际 JellyfinProxy 播放链（RO-4）与线上发布／推送／上架均不在本页范围，当前 NOT RUN。
