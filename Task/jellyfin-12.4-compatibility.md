# 独立修复 Task — Jellyfin 12.4 兼容性实测

```text
Task ID: FIX-JF-12.4
Parent Slice: NONE
Status: PASS
Task Base: 2d1b33eec8f06e98c50649fcfa35d81d19946402
Difficulty: Medium
Test Level: T3
```

## 目标与范围

在 Jellyfin 12.4.0／Linux x64 上，用已发布的 v0.1.0 ZIP 跑一次干净安装兼容性测试。复用 `package_environment.py`、`run_isolated_package_integration.py --scenario clean` 和现有浏览器驱动。允许调整隔离规格、镜像锁、版本校验和必要的验证工具。Slice 1～6 的接受记录与本 Task 分开。若实机发现产品问题，先固定原始结果与可复现证据，再确定修复范围。

Jellyfin 的发布标签为 `v12.4`，源码为 `83d0d0e7f76e23e2e085c8ff67d28b772d35967d`。本次使用 `jellyfin/jellyfin:12.4` 对应的 Linux amd64 digest，并核对服务报告的版本。见[官方发布](https://github.com/jellyfin/jellyfin/releases/tag/v12.4)。

## 验收条件

1. 专用工作区和本机回环端口上启动固定镜像。安装原 ZIP，插件为 Active，部署文件摘要匹配。
2. 原生 Web 播放合成 MP4 和 MKV，画面与时间实际推进。首次信任与原样复查均跳过插件探测。从配置页保存并读回，手动启动唯一且默认无触发器的原生任务。
3. MP4 内容 SHA-1 和 Size 相同、仅改变 URL，触发一次原生探测。PlaybackInfo 返回新地址及主流，指纹记录更新。重启后先用只读查询确认新地址和主流，核对指纹，再请求 PlaybackInfo，确认无需重探测。
4. 停止本次归属的实例，保留本机证据。非本 Task 验收项包括原生仓库安装、跨版本迁移、完整播放矩阵、千项容量、音频 STRM 与代理联调。

## Developer 开发指导

1. 在 `package_environment.py` 的版本表登记 12.4，固定官方 Linux amd64 镜像。沿用 `--scenario clean`、发布 ZIP 检查、浏览器驱动和原生任务入口。为 12.4 实测分配新工作区、独立 Compose 项目和空闲回环端口。[独立镜像锁](../dev/images-12.4.lock.json)
2. 在隔离库中先让 Jellyfin 保存合成 MP4／MKV 的主流，再启用插件验证首次信任。通过原生 Web 播放两份样本。将 MP4 的 STRM 改为指向字节相同的另一个地址，用已有 PlaybackInfo 请求验证一次探测与指纹提交。
3. 用本轮 Compose 项目重启后，先通过原生 `GET /Items` 读取新地址及 Video／Audio 流，再只读查 SQLite 的五字段指纹，最后请求 PlaybackInfo 并核对日志中的零探测。收尾时记录该项目两项服务的退出状态。

## 验证计划

- Developer 执行治理检查、`git diff --check`、包与播放相关的 Python 测试，以及 `python3 scripts/check_plugin_repository.py --package "$package"` 确认包身份。
- 核心实机命令为 `JF_PROBE_PACKAGE_PORT=18247 timeout 15m python3 scripts/run_isolated_package_integration.py --server-version 12.4 --scenario clean --package "$package" --evidence-dir "$evidence" --keep-workspace`。运行后使用本轮 Compose 文件与项目身份停止实例并记录退出状态。测试预算为 15 分钟，专用容器运行两份合成媒体，使用本机 Playwright 1.55.0。
- B 核对完整 Base..Head 和原始证据，独立运行同一 12.4 实机入口及默认 12.2 的干净安装场景。按[开发环境命令](../docs/development-environment.md#构建与隔离实例)运行完整 C#／Python 回归。默认 12.2 实例停止后再运行 Python 全量，包与扫描的清理测试会读取该 Compose 项目的容器状态。
- 证据保存于 `.git/validation-evidence/`，包含精确候选、工具摘要、包、镜像、命令、退出码和原始观测。保留首次失败，与重跑分开记录。

## 实施报告

2026-11-21 在 `e5d625e56dc64a13ceb1e47ff43e2b9dd6938766` 的干净检出上执行。改动集中于隔离测试输入、版本路由、逐轮 Compose 项目和干净安装场景的重启断言。

- **实机 PASS**。固定 Linux amd64 镜像报告 `12.4.0`。v0.1.0 发布 ZIP SHA-256 为 `9641fe917cc8db8d36ec32c841fb968b0149890f39094adce5338a0f28dd9e37`，归档结构及发布索引校验通过，8 个部署文件摘要匹配，插件安装与重启后均为 Active。
- MP4／MKV 的 H.264／AAC 样本通过原生 Web 播放，分别观测到 0.446／0.175 秒与 160×90 视频画面。配置页保存后重启成功读回。原生计划任务默认无触发，手动执行结果为 `Completed`。
- MP4 首次信任与原样复查日志各记录 0 次插件探测。仅换 URL 后，插件记录一次匹配的编码器探测，确认原生地址已保存并提交指纹。重启后先只读核对新 URL、Video／Audio 主流与五字段指纹，随后 PlaybackInfo 返回新源并记录 0 次插件探测。计数采用插件日志中的匹配调用。
- Python 聚焦回归 182/182 PASS（包环境 56 项，播放 126 项）。治理与 `git diff --check` 均通过。完整 C#／Python 回归和 B 独立复现为 NOT RUN。
- 本次实机一次完成，退出码 0。隔离 Jellyfin 和测试媒体服务均正常停止，退出码 0，未发生 OOM。测试工作区和原始记录留在本机。

证据索引位于 `.git/validation-evidence/e5d625e56dc64a13ceb1e47ff43e2b9dd6938766/jellyfin-12.4-clean/INDEX.md`。

## B 独立审查

审查范围为 `2d1b33eec8f06e98c50649fcfa35d81d19946402..87b071ef0a27153443082f93177bcd30e71b0d18`。**PASS，无阻塞项。** 核对了全部七个文件、Developer 原始结果、发布包摘要、官方标签和镜像索引中的 amd64 子镜像。实现差异集中在隔离工具、规格／锁和测试。

- 管理员在 Jellyfin 12.4.0／Linux x64 上安装原 v0.1.0 ZIP 后，插件为 Active，八个部署文件的摘要相符。配置页保存的值在重启后读回，原生计划任务唯一、默认无触发器，手动运行完成。用户从原生 Web 播放 MP4 和 MKV，浏览器均显示 160×90 视频并推进，实测读数为 0.537 秒和 0.554 秒。
- 同一部 MP4 首次信任和原样复查均为零次插件探测。内容、SHA-1 和大小相同，仅换地址后记录一次匹配的编码器调用、地址保存和指纹提交。重启后先读到新地址、Video／Audio 主流及换址后提交的五字段指纹，再请求 PlaybackInfo，日志明确记录零次插件探测。
- 12.4 冒烟及默认 12.2 干净安装均通过，两轮 Jellyfin 与媒体容器全部正常退出，无 OOM。固定 .NET SDK 10.0.401 的锁定还原、Release 构建、205 项 C# 测试和格式检查通过。Python 3.11.10 全量单独重跑为 467 项通过、零跳过。首轮并行执行时，三项清理用例读取了仍在运行的 12.2 容器，停止该轮容器后，同一候选复跑通过。
- 本轮复核超过 7 分钟。测试按实际经过时间合计约 3 分 28 秒，并行命令的重叠时间只计一次，占比低于 50%。

本次接受 Jellyfin 12.4.0／Linux x64 的原 ZIP 干净安装冒烟。独立 Task 到此结束，当前没有后续实施。B 的实机结果、容器日志、回归及首轮记录见本机 `.git/validation-evidence/87b071ef0a27153443082f93177bcd30e71b0d18/b-review-20261121T093541Z/INDEX.md`。
