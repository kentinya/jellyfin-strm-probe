# Task 1.1 — V4.2 核心接入原型与可靠指纹提交验证

Task 1.1 已由用户激活。本轮完成官方源码定位与环境诊断，但缺少 .NET SDK 和可访问的隔离 Jellyfin，无法安全验证核心接入与原生探测结果。没有创建插件源码；产品验收仍未运行，现交 B 审查阻塞及可复核证据。

```text
Task ID: 1.1
Parent Slice: 1
Status: READY FOR B REVIEW
Task Base: b69a930495c762fe546f8970891a2c955766b28c
Contract Checkpoint: 4a8536860fafaf25f7a1e573fef19255ca3d07c3
Superseded Plan: 4b1d0468c1e43e6e9034ef98e99b6cc44ea59485
Difficulty: High
Test Level: T4
Planner / Reviewer: B
```

## B 重规划决定

Decision: REPLAN。原 Task 1.1 是未实施计划，保留 ID／Task Base 供历史与审查追溯，明确以 Contract Checkpoint 中的新合同约束实施。原目标中的仅更新路径分支失效，替代为同 SHA-1 换 URL 也原生探测；指纹提交原型不维护独立状态机。没有产品实现或旧 PASS 可复用。

保留原生接入、可靠成功信号、播放地址持久化的验证责任及 T4 门槛；完整批量运行仍属于 Slice 3。本决定是计划调整，不是 B 产品审查 PASS。

## Goal

在一个固定 Jellyfin 版本上建立可加载的最小原型，完成 Slice 1 的 RO-1～RO-4，并为 RO-5 提供可信接入、结果提交、原生持久化与任务接口调研结论；核心风险成立后才进入完整产品开发。

## 实际缺口

没有 C# 项目、固定 SDK／包依赖或隔离实机证据。V4.2 示例尚不是经过验证的插件代码；任务源码本轮未取得，版本定位见 [compatibility.md](docs/compatibility.md) 与 [references.md](docs/references.md)。

## 实施范围

- 固定一个隔离服务器／镜像 digest、源码 SHA、目标框架、SDK 和依赖；优先调研 V4.2 引用的 v12.2，实际不匹配时先记录理由与目标选择，不宣称多版本兼容。
- 创建真实 solution、最小插件和必要测试项目；未来实际创建后补入准确 restore／build／test／format 命令，不虚构不存在的命令路径。
- 验证 Plugin／ServiceRegistrator 和候选 IMediaSourceManager 接入，完整委托、原生实例与释放所有权、启动／关闭、普通媒体／直播。
- 用手写版本化 STRM 和假／本地媒体服务，验证未变化跳过、必要主流缺失／指纹变化主动原生探测、URL 改变且 SHA-1 相同也实际探测。
- 验证 NativeProbeExecutor 能关联本次结果和原生保存，建立最小指纹提交原型；覆盖失败后旧流仍在、取消、Manifest 再变及保存失败，不增加持久化独立状态机。
- 证明 URL 变化后原生保存地址／有效主流，当次与重启正确；覆盖 allowMediaProbe=false 及回退权限。
- 核实目标版本的任务接口、注册方式、取消／进度及默认触发规则，记录 Slice 3 可行性；本 Task 不实现批量任务。
- 保存实际计数、日志、构建／加载证据、FullRefresh 附带开销与继续／调整结论。

范围包括必要的 Interceptors／Services 原型和隔离验证工具；完整解析器／SQLite 产品实现、全局并发与任务 UI 均延期。Task 内不更改 Slice Base、Required Outcomes 或验收。

## 验收条件

- [ ] RO-1／AC-1：目标版本与依赖准确，真实原型可构建／加载／正常启停。
- [ ] RO-2／AC-2：全接口委托、原生实例唯一、无循环／重复释放；普通媒体、直播、旧 STRM、禁用与原生刷新对照正常。
- [ ] RO-2／AC-3：未变化且已有主流的第二次播放实际 ffprobe 零增量；变化时确有新增执行。
- [ ] RO-3／AC-4：本次成功、旧流保留的失败、取消、文件再变与保存失败可靠区分；变化指纹仅在有效结果已保存且版本一致后提交，无法证明则报告阻塞。
- [ ] RO-4／AC-5：URL 改变且 SHA-1 相同实际探测，当次和重启均新 URL／有效主流，不以仅更新路径代替。
- [ ] RO-4／AC-6：allowMediaProbe=false 所有分支不主动探测、不提交变化基线；保存失败不把旧地址伪报为新地址；无独立状态机。
- [ ] RO-5／AC-7：固定源码接口定位、脱敏原始证据、额外开销、未完成项与继续／调整结论真实；不把调研当成任务实机验收。
- [ ] 真实完成 T4 指定门槛，提交实现 SHA；不自行签发 B PASS 或 A Final Review。

## 必要测试

V4.2 是验收含义变化，已由 B 重规划；保留原 Task 的四阶段测试安排和全部 T4 门槛，更新 T08／T22 与指纹断言。当前没有 C# 工程，准确 .NET 命令在固定版本并创建项目后补入。

### 开发／修正反馈

先运行新增／修改的原生委托、探测结果关联、指纹条件提交与最新地址测试，以及直接受影响回归。修正先重现失败；接入、原生保存或权限变化补相关隔离 Jellyfin 链路。纯假对象只能检验控制逻辑，不替代实际接入／成功／重启证据。

### 最终检查点门槛

真实项目创建后填写固定 SDK 的 restore、Release build、全部已有 test 和相关 format／分析器命令。核心服务替换、刷新、持久化和播放属于 T4，最终候选必须完整回归；套件已覆盖的聚焦用例记录覆盖关系，不机械重复。

仓库门槛：`python3 scripts/check_governance.py`、`python3 -m unittest discover -s tests -v`、`git diff --check`。

单独的真实门槛映射：

| 风险／行为 | 矩阵 | Slice 验收 |
|---|---|---|
| 构建／加载／启停、普通／直播／旧 STRM／禁用完整委托 | T23、T24、T26、X02 | AC-1、AC-2 |
| 未变化跳过与主动探测 | T01～T04、T08、X07 | AC-3 |
| 真成功、失败旧流仍在、取消、Manifest 再变、原生保存失败 | T17、T18、X04、X07、X08 | AC-4 |
| 同 SHA-1 换 URL 必探测，新地址当次及重启 | T08、T22、X04 | AC-5 |
| 原生手动刷新、allowMediaProbe=false 全分支、不建状态机 | T21、T28、X06 | AC-6 |
| 证据、FullRefresh 开销、任务接口源码定位与继续结论 | X07、源码调研记录 | AC-7 |

T19 在本 Task 验证原型结果／地址重启，不宣称完成 Slice 2 的正式 SQLite 验收。完整 T01～T28 属于 Slice 2；B01～B12 的批量与全局并发产品验收不提前算通过。

### B 独立验证

审查真实 Task Base..Implementation Head，并明确使用上述 Contract Checkpoint 的合同。独立复现未变化／主动探测实际计数、失败保留旧流时不提交新指纹、同 SHA-1 换 URL 必探测且当次／重启正确，以及 allowMediaProbe=false 对照。

其他构建／回归证据只有在输入匹配、原始产物可读时明确复用；缺失、矛盾或不可关联时重跑。核对任务接口调研，不将其作为原生计划任务已运行的证明。

### 证据与重跑规则

按 [开发流程](docs/development-workflow.md) 保留候选 SHA、工作区内容身份、版本／依赖／夹具摘要、精确命令、实际计数／耗时、首败／重跑、原始日志与未完成项；存放稳定的 `.git/validation-evidence/<source-sha>/<run-id>/` 或 CI 产物，日志脱敏。

可执行代码、测试、工具、依赖或运行输入变更后更新证据；T4 修正候选完成全部最终门槛。纯文档后继提交核对输入不变并重跑相关治理。Slice Final 另行执行新合同最终验证。

当前产品门槛全为 NOT RUN；缺 SDK／环境／成功信号如实报告，不用文档治理通过代替。

## 非目标

- 正式解析／全决策矩阵、SQLite schema／迁移、通用同源协调与全局并发产品实现：Slice 2。
- IScheduledTask 运行、停止、定时、分页范围、进度／统计、完整配置页面：Slice 3。
- 大规模／扫描／代理联调、发布包与多版本兼容：Slice 4。
- 生成器、OpenList API、媒体下载哈希、代理改造、独立调度器／探测状态机、仅更新路径服务、首版扫描后自动触发。

## Developer Completion Report

本报告交接环境阻塞，不表示 Task 产品目标已完成、Slice 验收通过或兼容性已确认。

### Changed Files

- `docs/compatibility.md`：记录 v12.2 源码路径、`net10.0` 目标框架及实测环境限制。
- `docs/references.md`：添加官方发布／源码定位和读取状态。
- `TASK.md`：记录本报告及 B 审查状态。Task 激活的 `IN PROGRESS` 是本轮开始前用户已有改动，现作为此 Task 检查点的一部分保留。
- 本地原始验证记录：`.git/validation-evidence/0167aadc88d5ec4998a116e7457cf8c80ab6bcee/task-1.1-env-blocker-20261013/`（仅本机，不是远程 CI 产物）。

### Implemented

- 依据官方 v12.2 源码确认候选播放入口会在允许探测时对 `.strm` 触发 `FullRefresh` 并重读媒体源；Provider 路径会调用原生 `ProbeVideo`。Controller 项目目标框架为 `net10.0`。
- 检查 Task Base 仓库树及当前容器能力，确认没有 C# 工程、.NET SDK／编译器或可访问的 Docker daemon。
- 没有创建或修改产品代码；没有使用生产 Jellyfin、生产媒体或生产配置。

### Tests and Results

- `python3 scripts/check_governance.py` — PASS；只验证文件治理，不代表产品实现通过。
- `python3 -m unittest discover -s tests -v` — PASS，24/24；仅为治理测试。
- `git diff --check` — PASS。
- 首次证据采集脚本在启动缺失的 `dotnet` 时未捕获 `FileNotFoundError` 并退出 1；治理、单元测试和差异检查的独立原始日志均已保留并显示 exit 0。该采集器错误记录在证据目录，没有把它算作产品测试结果。
- 固定 SDK 的 `dotnet restore`／Release `build`／`test`／`format` — BLOCKED：`dotnet`、`csc`、`mcs`、`msbuild`、`mono`、`nuget` 不存在，且尚无 solution／project。
- 隔离 Jellyfin 加载、真实探测／失败／取消／Manifest 竞态、播放地址保存及重启 — BLOCKED：Docker CLI 无法访问 `/var/run/docker.sock`；没有替代隔离服务器。
- T01～T28、B01～B12、X01～X10 的产品验收 — NOT RUN。上述浏览器源码定位不是实机验证。

### Decisions

- 停止受影响的插件实现：RO-1～RO-4 依赖先完成构建和隔离原生链路验证；在缺少工具及服务时创建未编译的替换实现，无法满足合同，也不能证明核心风险成立。
- 未自行改选 Jellyfin 版本、SDK、DI 方案或成功信号；v12.2 仍为候选，`.NET` 固定 SDK、服务器镜像 digest、依赖和可加载包均未确定。
- 不声明 B PASS，不更新 `SLICE.md` 的 Implementation Head，不关闭 Slice。请 B 根据证据决定如何解除环境阻塞或是否需要调整当前 Task。

### Remaining In-Slice Work

- RO-1／AC-1：固定服务器镜像 digest、源码、SDK、依赖和真实原型，全部未完成。
- RO-2／AC-2～AC-3：DI 所有权、全接口委托、正常播放及跳过／主动探测计数，全部未完成。
- RO-3／AC-4：本次成功／失败／取消／Manifest 再变与保存关联，全部未完成。
- RO-4／AC-5～AC-6：URL 变化原生探测、新地址保存／重启、`allowMediaProbe=false` 对照，全部未完成。
- RO-5／AC-7：仅完成部分源码与环境定位；任务接口、构建／加载、原始实机证据、FullRefresh 开销和继续／调整结论未完成。

### Risks / Deviations

- 主风险是缺少运行环境，无法给出接入可靠性、探测成功信号、播放行为或地址持久化结论；此检查点仅包含文档调查与阻塞证据。
- 单元／治理 PASS 不可复用为任何产品或 Jellyfin 集成门槛；T4 全套最终验证尚未开始。

```text
Head SHA: 0167aadc88d5ec4998a116e7457cf8c80ab6bcee
Product implementation SHA: NOT SET
```

## A 环境交接（2026-10-13）

用户要求 A 为开发者提供必要环境。已提供 [准备与运行说明](docs/development-environment.md)、固定 SDK `10.0.401`／官方 SHA-512、仓库内安装与离线归档入口、镜像 digest 锁定、隔离 Jellyfin／本地媒体服务 Compose 和统一 dotnet 入口。实际安装下载受 DNS 限制，Docker socket 拒绝访问，本地监听 socket 被禁止，环境仍 BLOCKED。镜像 digest、插件依赖和真实产品门槛仍未取得；原 Developer 报告保留，不把准备工具当成产品实现。

A 保持 Slice／Task 的 ID、Base、Scope、T4 验收与 B 独立审查责任；本段是环境事实交接，不是 B Review。Task 仍 READY FOR B REVIEW；具备宿主执行能力后可继续原已授权 Task 的环境验证及实施。详细本机证据索引见环境说明。

## B Review Result

```text
Reviewed: NOT SET
Decision: PENDING
Slice Required Outcomes all satisfied: PENDING
Next: PENDING
```

产品审查尚未开始；上方 REPLAN 只是对新合同的计划决定。
