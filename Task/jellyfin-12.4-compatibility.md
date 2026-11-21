# 独立修复 Task — Jellyfin 12.4 兼容性实测

```text
Task ID: FIX-JF-12.4
Parent Slice: NONE
Status: READY FOR B REVIEW
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

## 验证计划

- Developer 执行治理检查、`git diff --check`、包与播放相关的 Python 测试，以及 `python3 scripts/check_plugin_repository.py --package "$package"` 确认包身份。
- 核心实机命令为 `JF_PROBE_PACKAGE_PORT=18247 timeout 15m python3 scripts/run_isolated_package_integration.py --server-version 12.4 --scenario clean --package "$package" --evidence-dir "$evidence" --keep-workspace`。运行后使用本轮 Compose 文件与项目身份停止实例并记录退出状态。测试预算为 15 分钟，专用容器运行两份合成媒体，使用本机 Playwright 1.55.0。
- 独立审查按开发流程核对本次范围、固定输入、实机结果和已有回归。如需正式 B PASS，执行完整 C#／Python 回归、独立复现同一实机入口并核验本机原始证据。实机结果与独立审查分别记录。
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

PENDING。
