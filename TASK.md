# NO ACTIVE IMPLEMENTATION TASK

Task 1.1 已 PASS；Slice Final 已完成，Closure Packet 已交 A，无后继实施 Task。以下保留通过的 Task 与审查记录，供 A 核对。

# Task 1.1 — V4.2 核心接入原型与可靠指纹提交验证

Task 1.1 已由用户激活。B 已独立审查修正候选 `2b1e1b5bcf77b06997fabed5a31147838db16b47`，裁定 **PASS**；BR-1 保存关联与 BR-3 真实对照／FullRefresh 观察已满足，见下方 Current B Review Result。A 调整后的播放取消范围持续有效；BR-2 的历史 FAIL 保留，退出当前阻塞范围，不改写为修复或 PASS。全部 Slice 1 Required Outcomes／Surfaces 已核对满足，停止创建 Task，Slice Final 已完成，Closure Packet 见 SLICE.md；本 Task PASS 不关闭 Slice。

未移动 Base、未新建 Task，T4 等级与四阶段流程保留；按新合同调整取消验收范围。Developer 不签发 B PASS，不更新 Slice Implementation Head，也不关闭 Slice。

```text
Task ID: 1.1
Parent Slice: 1
Status: PASS
Task Base: b69a930495c762fe546f8970891a2c955766b28c
Contract Checkpoint: 4c749d7cce0f48b5c8146755db43837960e79f4f
Original V4.2 Contract Checkpoint: 4a8536860fafaf25f7a1e573fef19255ca3d07c3
Superseded Plan: 4b1d0468c1e43e6e9034ef98e99b6cc44ea59485
Difficulty: High
Test Level: T4
Planner / Reviewer: B
```

## B 重规划决定

Decision: REPLAN。原 Task 1.1 是未实施计划，保留 ID／Task Base 供历史与审查追溯，明确以 Contract Checkpoint 中的新合同约束实施。原目标中的仅更新路径分支失效，替代为同 SHA-1 换 URL 也原生探测；指纹提交原型不维护独立状态机。没有产品实现或旧 PASS 可复用。

保留原生接入、可靠成功信号、播放地址持久化的验证责任及 T4 门槛；完整批量运行仍属于 Slice 3。本决定是计划调整，不是 B 产品审查 PASS。

### B 对 A 取消语义澄清的接续决定（2026-10-13）

历史决定；取消防御及注入验收部分已由下方 ADJUST 替代。

Decision: CONTINUE。已在 A 合同提交 `0c2315ffa735694f4cae5a21771af9cc95c33488` 后运行治理检查，并核对 Required Outcomes／Surfaces、实际原型、既有失败复现和 Task 边界。澄清只明确取消对象和原生入口，Task 1.1 的 ID、Task Base、Goal、Scope、Difficulty、T4 与四阶段门槛保留，不重新规划。审查过的旧合同与实现 SHA 仍按原记录追溯。

播放接入保留原调用 token／权限；当前 PlaybackInfo 不传客户端取消，不新增停止播放事件或 `RequestAborted` 到探测的关联。未变化且已有主流仍跳过，启动 PlaybackInfo 不等于实际探测。客户端退出后，本次执行若成功、结果已保存且 Manifest 一致，仍可提交；执行本身收到取消时必须保留旧基线。真实取消验证在带可取消 token 的隔离 Jellyfin 原生执行链进行，并标明入口，不能声称验证了公共客户端取消。批量任务及通用共享协调仍延期。

BR-1 保存关联、BR-2 执行取消提交保护及 BR-3 缺失真实对照继续阻塞，状态保持 FIX REQUIRED。本轮仅合同与文档同步，未修改产品源码、重跑产品验收或签发 Task／Slice PASS。

### B 对 A 播放取消 RESCOPE 的调整决定（2026-10-13）

Decision: ADJUST。已在 A 合同提交 `4c749d7cce0f48b5c8146755db43837960e79f4f` 后运行治理检查 PASS，核对真实调用入口、原型与历史审查证据。Task ID、Base、Goal、Difficulty、T4 与四阶段流程保留；Scope／AC-4／最终测试计划按新合同移除当前播放成功返回后的额外取消防御及人为注入取消门槛。原 token／权限委托、取消异常处理与全部已有回归保留；新的可取消共享执行与批量停止分别在 Slice 2／3 验证。

BR-2 的假对象 FAIL 不是实现修复或 PASS，而是本场景不再属于当前合同阻塞；BR-3 仅移除注入取消缺口，其余指定真实对照、竞态及 FullRefresh 观察继续要求。BR-1 保存关联与 BR-3 继续阻塞，Task 仍 FIX REQUIRED；所有 RO／Surfaces 尚未满足，不创建下一 Task、不交 Closure Packet。本次没有产品源码修改或产品验收运行。

## Goal

在一个固定 Jellyfin 版本上建立可加载的最小原型，完成 Slice 1 的 RO-1～RO-4，并为 RO-5 提供可信接入、结果提交、原生持久化与任务接口调研结论；核心风险成立后才进入完整产品开发。

## 实际缺口（Developer 前轮）

没有 C# 项目、固定 SDK／包依赖或隔离实机证据。V4.2 示例尚不是经过验证的插件代码；任务源码本轮未取得，版本定位见 [compatibility.md](docs/compatibility.md) 与 [references.md](docs/references.md)。

## 实施范围

- 固定一个隔离服务器／镜像 digest、源码 SHA、目标框架、SDK 和依赖；优先调研 V4.2 引用的 v12.2，实际不匹配时先记录理由与目标选择，不宣称多版本兼容。
- 创建真实 solution、最小插件和必要测试项目；未来实际创建后补入准确 restore／build／test／format 命令，不虚构不存在的命令路径。
- 验证 Plugin／ServiceRegistrator 和候选 IMediaSourceManager 接入，完整委托、原生实例与释放所有权、启动／关闭、普通媒体／直播。
- 用手写版本化 STRM 和假／本地媒体服务，验证未变化跳过、必要主流缺失／指纹变化主动原生探测、URL 改变且 SHA-1 相同也实际探测。
- 验证 NativeProbeExecutor 能关联本次结果和原生保存，建立最小指纹提交原型；覆盖失败后旧流仍在、原生取消异常、Manifest 再变及保存失败，不增加持久化独立状态机。
- 播放沿用原 token／权限；原生抛出取消异常时不提交并传播。不新增成功返回后的取消检查，不要求人为注入取消单元／实机验收；客户端退出不单独阻止符合全部成功条件的提交。已有取消异常回归保留。
- 证明 URL 变化后原生保存地址／有效主流，当次与重启正确；覆盖 allowMediaProbe=false 及回退权限。
- 核实目标版本的任务接口、注册方式、取消／进度及默认触发规则，记录 Slice 3 可行性；本 Task 不实现批量任务。
- 保存实际计数、日志、构建／加载证据、FullRefresh 附带开销与继续／调整结论。

范围包括必要的 Interceptors／Services 原型和隔离验证工具；完整解析器／SQLite 产品实现、全局并发与任务 UI 均延期。Task 内不更改 Slice Base、Required Outcomes 或验收。

## 验收条件

- [ ] RO-1／AC-1：目标版本与依赖准确，真实原型可构建／加载／正常启停。
- [ ] RO-2／AC-2：全接口委托、原生实例唯一、无循环／重复释放；普通媒体、直播、旧 STRM、禁用与原生刷新对照正常。
- [ ] RO-2／AC-3：未变化且已有主流的第二次播放实际 ffprobe 零增量；变化时确有新增执行。
- [ ] RO-3／AC-4：本次成功、旧流保留的失败、原生取消异常、文件再变与保存失败可靠区分；变化指纹仅在有效结果已保存且版本一致后提交，无法证明则报告阻塞。客户端退出不单独否决有效成功提交。
- [ ] RO-4／AC-5：URL 改变且 SHA-1 相同实际探测，当次和重启均新 URL／有效主流，不以仅更新路径代替。
- [ ] RO-4／AC-6：allowMediaProbe=false 所有分支不主动探测、不提交变化基线；保存失败不把旧地址伪报为新地址；无独立状态机。
- [ ] RO-5／AC-7：固定源码接口定位、脱敏原始证据、额外开销、未完成项与继续／调整结论真实；不把调研当成任务实机验收。
- [ ] 真实完成 T4 指定门槛，提交实现 SHA；不自行签发 B PASS 或 A Final Review。

## 必要测试

V4.2 是验收含义变化，已由 B 重规划；保留原 Task 的四阶段测试安排和全部 T4 门槛，更新 T08／T22 与指纹断言。当前候选的最终命令固定如下：

### 开发／修正反馈

先运行新增／修改的原生委托、探测结果关联、指纹条件提交与最新地址测试，以及直接受影响回归。修正先重现失败；接入、原生保存或权限变化补相关隔离 Jellyfin 链路。纯假对象只能检验控制逻辑，不替代实际接入／成功／重启证据。

### 最终检查点门槛

核心服务替换、刷新、持久化和播放属于 T4，最终候选必须完整回归；套件已覆盖的聚焦用例记录覆盖关系，不机械重复。

```bash
bash scripts/dotnet-local restore Jellyfin.Plugin.StrmProbeOptimizer.sln --locked-mode
bash scripts/dotnet-local build Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore
bash scripts/dotnet-local test Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore
bash scripts/dotnet-local format Jellyfin.Plugin.StrmProbeOptimizer.sln --verify-no-changes --no-restore
python3 scripts/run_isolated_plugin_integration.py
```

仓库门槛：`python3 scripts/check_governance.py`、`python3 -m unittest discover -s tests -v`、`git diff --check`。

单独的真实门槛映射：

| 风险／行为 | 矩阵 | Slice 验收 |
|---|---|---|
| 构建／加载／启停、普通／直播／旧 STRM／禁用完整委托 | T23、T24、T26、X02 | AC-1、AC-2 |
| 未变化跳过与主动探测 | T01～T04、T08、X07 | AC-3 |
| 真成功、失败旧流仍在、Manifest 再变、原生保存失败；原生取消异常保留已有回归 | T17、T18、X04、X07、X08 | AC-4 |
| 同 SHA-1 换 URL 必探测，新地址当次及重启 | T08、T22、X04 | AC-5 |
| 原生手动刷新、allowMediaProbe=false 全分支、不建状态机 | T21、T28、X06 | AC-6 |
| 证据、FullRefresh 开销、任务接口源码定位与继续结论 | X07、源码调研记录 | AC-7 |

T19 在本 Task 验证原型结果／地址重启，不宣称完成 Slice 2 的正式 SQLite 验收。完整 T01～T28 属于 Slice 2；B01～B12 的批量与全局并发产品验收不提前算通过。

### B 独立验证

审查真实 Task Base..Implementation Head，并明确使用上述 Contract Checkpoint 的合同。独立复现未变化／主动探测实际计数、失败保留旧流时不提交新指纹、同 SHA-1 换 URL 必探测且当次／重启正确，以及 allowMediaProbe=false 对照。

其他构建／回归证据只有在输入匹配、原始产物可读时明确复用；缺失、矛盾或不可关联时重跑。核对任务接口调研，不将其作为原生计划任务已运行的证明。

按 A RESCOPE 区分上下文：公共 PlaybackInfo 的原生不可取消入口事实单独记录；不要求成功返回后的额外取消检查与人为注入取消实机验收。原 token／权限、原生取消异常保护和全部已有回归保留。可取消共享执行／批量停止在后续 Slice 验证，不提高 false 权限或添加客户端事件关联。

### 证据与重跑规则

按 [开发流程](docs/development-workflow.md) 保留候选 SHA、工作区内容身份、版本／依赖／夹具摘要、精确命令、实际计数／耗时、首败／重跑、原始日志与未完成项；存放稳定的 `.git/validation-evidence/<source-sha>/<run-id>/` 或 CI 产物，日志脱敏。

可执行代码、测试、工具、依赖或运行输入变更后更新证据；T4 修正候选完成全部最终门槛。纯文档后继提交核对输入不变并重跑相关治理。Slice Final 另行执行新合同最终验证。

Task 环境阻塞阶段的原始计划快照曾记录产品门槛全为 NOT RUN；该历史状态已由下方 Developer Rework Report 的候选证据更新，不代表本次最终结果。治理检查与文件测试仍不代替产品测试。

## 非目标

- 正式解析／全决策矩阵、SQLite schema／迁移、通用同源协调与全局并发产品实现：Slice 2。
- IScheduledTask 运行、停止、定时、分页范围、进度／统计、完整配置页面：Slice 3。
- 大规模／扫描／代理联调、发布包与多版本兼容：Slice 4。
- 生成器、OpenList API、媒体下载哈希、代理改造、独立调度器／探测状态机、仅更新路径服务、首版扫描后自动触发。

## Developer Rework Report: Task 1.1

本报告交付同一 Task 的修正候选供 B 独立审查，不是 B PASS、Slice Final 或 AC 自行验收。Task ID、Base、Contract Checkpoint、范围、T4 等级和四阶段流程未变。

### Checkpoint and changed files

- Product implementation SHA: `2b1e1b5bcf77b06997fabed5a31147838db16b47`（tree `5433e566cc5f4d9e32db409b08a51d262665bbc0`）。这是本轮源码、测试与隔离工具提交；本报告和 CURRENT 文档随后单独形成文档检查点。
- 修正 `ProbeExecutionContext`：关联本次 URL 的完整关键主流身份；仅在 Jellyfin `SaveMediaStreams` 和 `SaveItems` 原生调用成功返回后记录媒体流／地址保存；返回源的主流必须与本次结果及已保存主流匹配，STRM 内容须在探测期间稳定，方可条件提交内存指纹。
- `ServiceRegistrator` 包装 `IMediaStreamRepository` 和 `IItemPersistenceService` 的原生实现，同时保留现有媒体源管理器／编码器迁移、生命周期和委托。优化器日志只记录保存信号、调用计数和状态，不记录完整 URL 或路径。
- 新增保存调用异常不发成功信号、已保存旧主流不得接受新结果的单元回归；新增本地隔离媒体服务器，用安全计数和延迟端点触发可重复 Manifest 竞态；扩展隔离脚本验证普通／旧 STRM／Live TV／禁用／false 权限／手动刷新／FullRefresh 工作及恢复。
- 被测变更文件为 `src/Jellyfin.Plugin.StrmProbeOptimizer/Services/ProbeExecutionContext.cs`、`src/Jellyfin.Plugin.StrmProbeOptimizer/Services/StrmPlaybackOptimizer.cs`、`src/Jellyfin.Plugin.StrmProbeOptimizer/ServiceRegistrator.cs`、`src/Jellyfin.Plugin.StrmProbeOptimizer/Interceptors/MediaEncoderDispatchProxy.cs`、新 `src/Jellyfin.Plugin.StrmProbeOptimizer/Interceptors/ProbePersistenceDispatchProxy.cs`、`tests/Jellyfin.Plugin.StrmProbeOptimizer.Tests/PlaybackOptimizerTests.cs`、`scripts/run_isolated_plugin_integration.py`、新 `scripts/isolated_media_server.py`、`scripts/development_environment.py` 和 `dev/compose.yaml`。没有改 `config/alist.json`。
- 完整脱敏日志及索引位于 `.git/validation-evidence/2b1e1b5bcf77b06997fabed5a31147838db16b47/developer-t4-20261013/`，仅本机可读；不含凭据或完整签名 URL。

### Observed behavior

- 固定 SDK `10.0.401`、目标框架 `net10.0`、Jellyfin Controller／Model `12.2.0`、隔离 Jellyfin `12.2.0` 和源码 `ca0f16eb7c195f720a1493ed469a27c4657db0c6`。插件在实机隔离实例多次启动为 Active；禁用后 Jellyfin 原生播放仍可用，重新启用并重启后插件为 Active。
- 首次信任和未变化播放分别观察到 0 次匹配探测；同 SHA-1／Size 地址变化触发 1 次匹配探测，成功日志显示本次编码器主流、原生已保存主流、地址已保存及返回流匹配，PlaybackInfo 返回新地址与 Video／Audio 主流；服务器重启后新地址与主流仍可用。
- 新地址不可达时 PlaybackInfo 返回 HTTP 500，原生保存流摘要与失败前相同；重复请求继续探测。恢复旧地址需按 Jellyfin 实际路径再探测，之后播放恢复成功。
- 保存代理抛错时不会登记保存信号；单测模拟提供器吞掉保存异常后返回旧主流，优化器拒绝旧流并保留旧指纹。没有对隔离 Jellyfin 内部数据库执行故障注入；实机覆盖的是成功保存关联及失败 URL 保留旧流。
- 隔离实机覆盖普通媒体、未版本化 STRM、M3U Live TV auto-open／取源、插件禁用、真实 `allowMediaProbe=false` 的视频流端点、手动 FullRefresh，以及成功探测期间修改 STRM。竞态返回 HTTP 500、记录 1 次匹配调用且保留指纹；恢复到稳定 Manifest 后下一次探测成功。
- 手动 FullRefresh 返回 HTTP 204 并改变条目 ETag；该次没有本地媒体 GET 或进程级 `GetMediaInfo` 调用，之后地址变化的 PlaybackInfo 仍触发 1 次探测。地址变化探测路径另记录了 3 组同 SHA／Size 运行，每组 1 次匹配调用和 1 次媒体 GET；原始计数与约 60～90 ms 的合成 PlaybackInfo 时延在 JSON 中。它只说明固定本地夹具下的工作路径，不是通用性能结论。

### T4 verification

- `bash scripts/dotnet-local restore Jellyfin.Plugin.StrmProbeOptimizer.sln --locked-mode` — PASS。
- `bash scripts/dotnet-local build Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore` — PASS，0 warnings／errors。
- `bash scripts/dotnet-local test Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore` — PASS，32/32，0 skipped；包括保存关联、保存失败、旧流回退、取消异常、权限、Manifest 竞态和决策回归。
- `bash scripts/dotnet-local format Jellyfin.Plugin.StrmProbeOptimizer.sln --verify-no-changes --no-restore` — PASS。
- `python3 scripts/run_isolated_plugin_integration.py` — PASS，提交版最终运行恢复原 STRM、启用插件并验证 Jellyfin 地址同步。
- 最终文档更新后重跑 `python3 scripts/check_governance.py`、`python3 -m unittest discover -s tests -v`、`python3 -m py_compile scripts/run_isolated_plugin_integration.py scripts/development_environment.py scripts/isolated_media_server.py` 和 `git diff --check`；结果及退出码写入同一证据索引。文档提交不改可执行候选或其锁／夹具输入。
- 本地反馈阶段先后发现并修正插件列表匹配、失败 URL 后的原生恢复探测、FullRefresh 完成检测和 FullRefresh 观测区分问题；新增保存身份字段及保存异常测试时修正编译问题。未把这些失败算作最终 PASS；因最初交互执行未将每段终端原始输出重定向到文件，证据索引会明确标为会话输出摘录而非原始日志。

### Limits and handoff

- Jellyfin `12.2.0` 的公共 PlaybackInfo 固定传 `allowMediaProbe=true`／`CancellationToken.None`。false 权限通过固定源码所示、真实可取消的 `/Videos/{itemId}/stream?static=true` 入口验证；未声称测试了 PlaybackInfo false 参数或客户端取消探测。
- 进程内指纹仓库重启后重新首次信任；本轮重启只证明 Jellyfin 原生地址与媒体流持久化。正式 SQLite、完整决策矩阵、跨媒体源协调、全局并发、批量任务、配置页面、发布包、多版本兼容和外部 JellyfinProxy／OpenList 联调不在当前 Task 实现中。完整 T01～T28 与 B01～B12 矩阵未运行。
- 历史 B 决定 `FIX REQUIRED` 仍是最后一份独立审查结论；Developer 不改审查结果、不勾验收框、不更新 Slice Implementation Head、不规划下一 Task、不关闭 Slice。请 B 基于 Task Base `b69a930495c762fe546f8970891a2c955766b28c` 与 Contract Checkpoint `4c749d7cce0f48b5c8146755db43837960e79f4f` 审查新候选并裁定 BR-1／BR-3。

```text
Product implementation SHA: 2b1e1b5bcf77b06997fabed5a31147838db16b47
Evidence: .git/validation-evidence/2b1e1b5bcf77b06997fabed5a31147838db16b47/developer-t4-20261013/
Task status: READY FOR B REVIEW
Last independent B decision: FIX REQUIRED (on prior implementation SHA)
```

## Developer Completion Report: Task 1.1 initial implementation (superseded)

本报告提交固定候选供 B 独立审查，不是 B PASS 或 Slice Final。验收框仍由 B 对照 Contract 检查。

### Checkpoint and changed files

- Product implementation SHA: `153c0d31a699ff15047b6a2e274237497476ec76` (tree `06890347a0c359c7786de1d75c09b08179573012`). 后续本报告为文档检查点，不改可执行候选。
- 连贯本地提交：`6245586a69d9b289fbcb17162c545f0e08aa046e` 建立最小插件／测试；`073a747fbaac18f079b7b3b6fa150befcaba3482` 增加失败后媒体流保留实测；`55237a9d330070b9a569ef8ba2185b13c9e7e836` 覆盖探测成功但新地址未保存；`153c0d31a699ff15047b6a2e274237497476ec76` 覆盖传入 token 取消。
- 新增真实 solution、插件项目、`meta.json`、插件服务／拦截器、只读 STRM reader、决策服务、内存条件指纹仓库、执行上下文、29 项单元测试和隔离 Jellyfin 集成脚本。
- 更新 [架构](docs/architecture.md)、[兼容性](docs/compatibility.md) 和 [开发环境交接](docs/development-environment.md)，将 Task 原型实况与目标设计／历史阻塞分开记录。
- 最终原始验证索引：`.git/validation-evidence/153c0d31a699ff15047b6a2e274237497476ec76/developer-t4-20261013/INDEX.md`。只含脱敏输出、SHA 与调用次数；无凭据或完整媒体地址。

### Implemented and observed

- 固定 SDK `10.0.401`、`net10.0`、Jellyfin.Controller／Model `12.2.0`、源码 `ca0f16eb7c195f720a1493ed469a27c4657db0c6`；产品与测试项目均有 lock 文件。固定容器在隔离实例成功加载插件并三次启动为 Active。产品 DLL 和部署 DLL SHA-256 相同，记录于验证索引。
- `ServiceRegistrator` 在核心服务注册后用 DispatchProxy 包装 `IMediaSourceManager` 与 `IMediaEncoder`，迁移原生实现到其 concrete registration，保留原 lifetime／单例释放；所有未优化方法委托到原生服务。测试覆盖重复／异常注册、完整 manager 接口委托及释放所有权。
- 支持的版本化 `.strm` 才进入检查；解析只读、有界且纯本地。旧／非法／不可用 STRM、普通媒体、禁用设置和原调用 `allowMediaProbe=false` 保留原权限并委托。决定器先比较 URL，再仅在双方 SHA-1 均有效时比较内容；URL 相同且 SHA-1 相同忽略 Size，否则按有效 Size 判断。mtime 不触发。
- 原生刷新调用以 AsyncLocal 上下文关联目标 URL 的 `IMediaEncoder.GetMediaInfo`；只有本次返回必要主流、Jellyfin 返回和保存了新 URL／主流、Manifest 未变且条件提交成功才更新内存基线。初次接管已有主流只建立基线，不宣称探测成功。失败、取消、地址未保存、旧流返回、Manifest 竞态和条件提交竞争不接受变化基线；地址变化无法证明新结果时拒绝用旧地址成功返回。
- 隔离实测的首次接管与未变化播放分别为 0 次匹配探测；同 SHA-1、同 Size URL 变化为 1 次且返回新地址及 Video／Audio 流；新地址重启后仍可用，再次首信任为 0 次探测。
- 不存在的新 URL 实际触发 1 次探测后 HTTP 500；Jellyfin 保存流快照与失败前 SHA-256 完全相同；下一次仍触发 1 次重试。另有单测证明已观察到探测主流、但新地址未保存时不提交指纹且不返回旧地址。
- 固定源码任务接口调研已记录：`IScheduledTask` 提供进度、取消和默认触发；任务由 `ApplicationHost` 的 `GetExports<IScheduledTask>(false)` 加入 `TaskManager`；管理员 API 支持运行、停止和更新触发器；默认触发读取失败会回退每日触发，故无自动时间须返回空序列而不能抛异常。本 Task 未实现计划任务。

### Tests and results for the implementation candidate

- `python3 scripts/check_governance.py` — PASS；`python3 -m unittest discover -s tests -v` — PASS，30/30；`git diff --check` — PASS。
- `bash scripts/dotnet-local restore Jellyfin.Plugin.StrmProbeOptimizer.sln --locked-mode` — PASS。
- `bash scripts/dotnet-local build Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore` — PASS，0 warnings／errors。
- `bash scripts/dotnet-local test Jellyfin.Plugin.StrmProbeOptimizer.sln --configuration Release --no-restore` — PASS，29/29，0 skipped；包括取消 token、保存地址失败、探测失败、Manifest 竞态、探测权限与 URL／SHA-1／Size 决策。
- `bash scripts/dotnet-local format Jellyfin.Plugin.StrmProbeOptimizer.sln --verify-no-changes --no-restore` — PASS。
- `python3 scripts/development_environment.py doctor` — PASS，10/10；隔离 Jellyfin status healthy。`python3 -m py_compile scripts/run_isolated_plugin_integration.py` — PASS。
- `python3 scripts/run_isolated_plugin_integration.py` — PASS；真实计数、事件、重启、失败、旧流快照与单次端到端时延见原始脱敏 JSON。URL 变化请求为 1169 ms，随后未变化请求为 49 ms；仅作调用路径观测，不是 FullRefresh 性能基准。

### Limits handed to B

- 单元测试用传入的 CancellationToken 取消执行并验证基线保留。目标版本 PlaybackInfo 调用上游传 `CancellationToken.None`；唯一带请求取消 token 的可取消取源调用传 `allowMediaProbe=false`，本插件必须原样保留该权限。因此真实 PlaybackInfo 活跃探测取消为 BLOCKED／NOT RUN；没有通过私有测试接口伪造线上调用路径。
- 已测试“成功编码器结果但新地址未保存”的拒绝逻辑；没有故障注入到 Jellyfin 内部数据库／保存层。
- 普通媒体、旧 STRM、插件配置关闭、`allowMediaProbe=false` 及 live-stream 方法走委托路径有单元测试，但没有分别对 Live TV／各播放 API 做实机运行。实机集成聚焦版本化 STRM PlaybackInfo。
- 指纹仓库是 Task 原型允许的进程内最小实现，重启后重新信任接管；正式 SQLite、完整决策矩阵、跨媒体源共享协调、并发限流、批量任务／配置 UI、发布包均未实现。本次重启只实证 Jellyfin 原生播放地址与媒体流持久化。
- 本次没有外部 JellyfinProxy／OpenList 联调；未执行完整 T01～T28 或 B01～B12 矩阵。
- 早期开发反馈中曾修正 Jellyfin API 类型／测试代理编译问题及一条 Manifest 再变测试失败；这些交互期原始 stdout 未保存。最终固定候选的全套原始门禁日志已留存，未将早期失败隐藏成 PASS。

### Developer handoff

当前代码与规定门禁已按上述 SHA 完整复验，工作树干净。请 B 基于原 Task Base 和 Contract Checkpoint 独立核对差异、复现跳过／同 SHA 地址变化探测／失败保流重试／探测与地址保存条件，并裁定上述限制对 AC-2／AC-4／AC-6 的影响。本状态仅表示交接 `READY FOR B REVIEW`，不自行满足验收勾选、不声明 Task PASS、不改 Slice Implementation Head、不关闭 Slice。

```text
Product implementation SHA: 153c0d31a699ff15047b6a2e274237497476ec76
Evidence: .git/validation-evidence/153c0d31a699ff15047b6a2e274237497476ec76/developer-t4-20261013/
Task status: READY FOR B REVIEW
```

## Developer Completion Report — Environment Blocker (historical, superseded)

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

用户要求 A 为开发者提供必要环境。已提供 [准备与运行说明](docs/development-environment.md)。用户调整权限并恢复会话后，SDK `10.0.401` 下载／官方 SHA-512 校验／安装、固定源码检出、镜像 digest 锁定、Jellyfin `12.2.0` 启动、本机访问、原生 HTTP 媒体探测均已实测。忽略目录内 `Jellyfin.Controller`／`Jellyfin.Model` `12.2.0` 引用样例已 restore／Release build／运行，0 编译警告／错误，nuspec repository commit 与固定源码一致。已准备仅属于测试实例的账户、临时库和合成媒体；口令只存忽略目录，不进入提交或证据。修正首次纯内部网络未发布宿主端口的问题，并保留首次失败与重跑。环境阻塞已解除；产品项目、产品依赖锁和全部核心 T4 门槛仍未完成。

A 保持 Slice／Task 的 ID、Base、Scope、T4 验收与 B 独立审查责任；本段是环境事实交接，不是 B Review。Task 仍 READY FOR B REVIEW；B 可核查环境证据后由 Developer 恢复原已授权 Task 实施。详细本机证据索引见环境说明。

## Previous B Review Result (environment handoff)

```text
Reviewed: b69a930495c762fe546f8970891a2c955766b28c..1035b1b3d31d88cde1a47154f24597d120530380
Contract Checkpoint: 4a8536860fafaf25f7a1e573fef19255ca3d07c3
Product implementation SHA: NOT SET
Decision: FIX REQUIRED
Slice Required Outcomes all satisfied: NO
Next: Developer resumes Task 1.1 as IN PROGRESS
```

### 审查范围与结论（2026-10-13）

用户要求本轮按 B 职责处理。已检查真实 Task Base..Reviewed 差异、已提交 V4.2 合同、前轮阻塞报告及 A 的原始环境日志；初始 `git status --short --branch` 为干净的 `main`。当前 Task 身份、Base、Goal、Scope 与验收仍合法，无须重新规划或申请原已授权范围。

**环境阻塞已解除，允许继续原 Task；Task 产品目标未完成，不能签发 PASS。** 本会话前轮承担 A 环境准备，本轮是环境交接复核和 B 接续决定；没有被审查的产品实现，也不宣称已完成独立产品关键行为验证。未来候选仍须满足本 Task 的 B 独立验证责任。

### 证据核验与本轮复测

- A 索引的 13 项输入摘要与交接提交、当前文件和保存的快照一致；样例源码／项目／依赖锁、两份媒体夹具和镜像锁与证据一致。检查首次网络、授权头及停止期间命令失败和成功重跑，未将首败算为 PASS。
- 本轮 `doctor` 10/10 PASS；固定 SDK 为 `10.0.401`，源码检出 HEAD 与合同记录一致且源码工作区干净；运行容器镜像引用匹配 digest 锁，挂载均属于隔离目录，媒体只读，发布端口为 `127.0.0.1:18096`。
- 本轮样例 `restore --locked-mode`、Release build／run 均 PASS，0 编译警告／错误；两包 nuspec repository commit 与固定源码一致。样例仍在忽略目录，不能计为可加载产品插件。
- 当前 Public Info 为 `12.2.0`，Jellyfin healthy；测试账户登录、两个临时库及远程提供器／插件仓库禁用配置核验 PASS，凭据权限 `0600` 且被 Git 忽略。原生 HTTP ffprobe 返回 H.264／AAC；这只验证基础媒体链路，不是插件主动探测计数或本次成功信号。
- 治理检查 PASS、工具回归 30/30 PASS（0 跳过）、Task Base..Reviewed 空白检查 PASS。纯文档审查后继不改变上述可执行输入，复用这些运行；变更文档消费的治理及差异检查另行执行。
- A 的停止／启动原始日志和身份／配置恢复记录作为环境历史证据保留；本轮没有再次重启。插件播放地址／主流重启验收仍 NOT RUN。

本轮原始本机证据：`.git/validation-evidence/1035b1b3d31d88cde1a47154f24597d120530380/b-env-review-20261013/index.json`。保留精确命令、退出码、耗时、原始输出、输入身份和被审查差异；仅本机可读，不是远程 CI。

### 当前 Task 阻塞项与 Required Outcomes

| 项 | 当前事实与必须补齐的结果 |
|---|---|
| RO-1／AC-1 | 环境已具备；仍缺真实 solution、产品依赖锁、最小插件／测试项目和构建／加载／启停证据。官方镜像没有 revision 标签，不能仅凭版本号认定整体源码身份；补齐目标二进制／源码关联证据并披露限制。 |
| RO-2／AC-2～AC-3 | 原生实例唯一、DI／生命周期／全接口委托、普通／直播／旧 STRM／禁用对照及实际跳过／主动探测计数均 NOT RUN。 |
| RO-3／AC-4 | 本次成功且已保存的关联信号、失败保留旧流、取消、Manifest 再变及保存失败的条件提交均 NOT RUN。 |
| RO-4／AC-5～AC-6 | 同 SHA-1 换 URL 必须实际探测、当次 PlaybackInfo 与重启新地址／有效主流、allowMediaProbe=false 各分支均 NOT RUN。 |
| RO-5／AC-7 | 已有部分接口与环境定位；仍缺完整任务接口调研、FullRefresh 开销、原型构建／加载及核心行为证据和继续／调整结论。 |
| T4 最终门槛 | 产品项目未创建，产品 restore／build／test／format、真实集成及 B 独立关键行为验证均 NOT RUN。现有工具和环境样例 PASS 不能代替。 |

### Developer 接续要求

1. 接手时记录 Git 状态并运行治理检查，将原 Task 1.1 改为 `IN PROGRESS`。沿用既有合同和 [环境说明](docs/development-environment.md)，不新建 Task、不变更 Base／Scope／T4。
2. 先创建可构建／加载的最小插件及必要测试，提交固定产品依赖锁和真实命令；实证 DI、单例所有权、完整委托及正常启停。核心接入不成立时报告阻塞，不铺开 Slice 2／3。
3. 按原验收和四阶段测试计划完成探测计数、本次成功／保存关联、失败／取消／竞态保护、URL 变化当次与重启、探测权限对照，以及任务接口和刷新开销调研。不得用旧流或刷新返回值冒充本次成功。
4. 完成候选的全部 T4 指定门槛，保存准确实现 SHA、输入身份、脱敏原始日志及未完成项；更新完成报告并交为 `READY FOR B REVIEW`。B 再独立复现指定关键行为；全部 Slice Outcomes 满足后才提交 A 最终审查。

<a id="current-b-review-result"></a>
## Current B Review Result

```text
Reviewed: b69a930495c762fe546f8970891a2c955766b28c..2b1e1b5bcf77b06997fabed5a31147838db16b47
Report Checkpoint: fe8399b9dc1cbde6f2f74917511a60faa5b4ac3e
Reviewed Contract Checkpoint: 4c749d7cce0f48b5c8146755db43837960e79f4f
Decision: PASS
P0/P1 Blockers: NONE
Slice Required Outcomes all satisfied: YES
Next: SLICE READY FOR A REVIEW; Slice Final and Closure Packet in SLICE.md; no next Task
```

### 独立审查与证据（2026-10-13）

本轮开始工作区为干净 `main`，治理检查 PASS。检查真实 Task Base..Implementation SHA：其中既有合同／环境检查点与实施提交分别追溯；修正没有越出 Task 1.1，没有正式 SQLite、协调器、批量任务或生成器实施。报告检查点与实现检查点的差异只有四份文档，可执行源码、工具、锁与运行夹具定义不变。独立验证使用报告检查点，接受的 Implementation Head 仍为实际实现提交。

证据索引：`.git/validation-evidence/2b1e1b5bcf77b06997fabed5a31147838db16b47/b-review-20261013/INDEX.md`，仅本机可读。保留全部跟踪输入摘要、精确命令、退出码、耗时、原始脱敏输出、独立 harness 及临时诊断配置摘要。Developer 原始日志已阅读；本轮关键行为及最终命令独立运行，不仅复用其 PASS 标签。B 构建／部署 DLL 摘要及与 Developer 构建的关系见索引，不由源码相同推定二进制相同。

- locked restore、Release build、全套 C# 回归 32/32（0 failed／skipped）、format verify、工具回归 30/30（0 failed／skipped）及差异检查 PASS，构建 0 warnings／errors。
- 隔离集成独立运行 PASS：首次信任／未变化均 0 次匹配调用；同 SHA-1／Size 换 URL 为 1 次，本次编码器主流、已保存主流、地址保存和返回流匹配，提交指纹；当次及真实重启后均返回新 URL 与 Video／Audio 主流。重启后的重新信任只证明 Jellyfin 持久化，不证明插件指纹持久化。
- 不可达 URL 两次均 HTTP 500／1 次匹配调用，原生旧流摘要不变；稳定恢复后成功。Manifest 探测中再变为 HTTP 500／1 次调用、不提交，后续重试成功。普通文件、Live TV auto-open／取源、旧 STRM、禁用及恢复、真实 false 权限流入口和手动 FullRefresh 均通过独立对照。
- B 独立 harness 覆盖流保存抛错但返回与本次结果相同的旧主流、地址仅在内存更新、条目保存抛错。每种均连续两次拒绝变化地址、保留旧基线，false 请求保留权限。该 harness 只验证控制边界，不冒充 Jellyfin 内部数据库故障注入。
- 独立 FullRefresh 提供器观察：隔离实例临时将已有默认日志级别设为 Debug，两次地址变化均执行 `ProbeProvider`、`MovieNfoProvider`、`TrickplayProvider` 各一次，条目 ETag 改变，1 次匹配探测和 1 次合成媒体 GET；PlaybackInfo 为 91／75 ms。原日志级别及 STRM 均已恢复并同步播放地址。仅保存提供器名和项目身份摘要，原生私有路径未进入证据。日志证明提供器被调用，不证明其完成远程下载或生成 Trickplay，也不提供开销分项／通用性能承诺。

### 原阻塞裁定与 Required Outcomes / Surfaces

| 项 | 本轮决定与依据 |
|---|---|
| BR-1 | RESOLVED。保存代理在原生成功返回后才记信号，按项目与本次主流身份关联；变化 URL 单独要求地址保存。固定源码 `MediaStreamRepository.SaveMediaStreams` 在事务 Commit 后返回；`ItemPersistenceService.SaveItems` 经 `UpdateOrInsertItems` 的 SaveChanges／Commit 返回，保存错误不被这两层吞掉。上层提供器吞错仍不会产生保存信号。独立失败 harness、既有回归及真实成功／重启链路共同成立，不再靠旧主流存在或内存 ShortcutPath 推定保存。 |
| BR-3 | RESOLVED。指定真实委托、权限、手动刷新、Manifest 竞态及恢复均独立复验；提供器日志补足 FullRefresh 附带工作观察。 |
| BR-2 | OUT OF CURRENT SCOPE，沿用 A RESCOPE；旧 FAIL／NOT RUN 原样保留。原生 token 委托和取消异常保留基线的已有回归 PASS，不新增注入取消验收。 |
| RO-1／AC-1 | 满足：真实项目、SDK／依赖锁、源码／镜像固定与构建／加载／启停证据。镜像缺 revision 标签的整体源码溯源限制仍披露。 |
| RO-2／AC-2～AC-3 | 满足：接口委托／单例释放回归、固定源码注册与实机生命周期、普通／直播／旧媒体／禁用对照、跳过／主动探测计数。 |
| RO-3／AC-4 | 满足：本次结果与事务保存关联、失败旧流、Manifest 竞态、条件提交、取消异常及保存失败边界；允许原型存储，不计正式 SQLite。 |
| RO-4／AC-5～AC-6 | 满足：同 SHA 换 URL 探测、当次／重启地址与流、保存失败拒绝／重试、false 权限及原生手动刷新。 |
| RO-5／AC-7 | 满足：固定源码任务接口定位、可核验证据、附带提供器观察及限制。继续结论为“核心原型可交 A 最终审查”；后续产品 Slice 仍须 A 关闭／激活。 |

全部 Required Surfaces 已具备：真实项目／验证入口、隔离加载与 PlaybackInfo 原生链、本次探测计数及保存／重启证据、可重复提交条件和目标任务接口调研。无需按字段、测试或模块再造 Task；下一步运行当前合同的 Slice Final，不能直接复用 Task 运行充当最终门槛。

非阻塞限制：进程内 `primary` 原型不具备正式指纹重启、通用多源共享／并发；内部数据库故障未实机注入；合成短媒体与禁用远程提供器的环境不代表生产性能／广泛媒体兼容；完整矩阵、批量、代理和发布均延期。收尾经验候选为“提供器吞错时，在实际保存事务边界取证”和“测 FullRefresh 附带工作时，计数配合提供器日志且区分调用与完成”；由 A 关闭时合并，不写入角色经验流水账。

## Last B Review Result (prior implementation)

```text
Reviewed: b69a930495c762fe546f8970891a2c955766b28c..153c0d31a699ff15047b6a2e274237497476ec76
Report Checkpoint: e005dbdcbd76fe983710721f106a5ccc02eff63f
Reviewed Contract Checkpoint: 4a8536860fafaf25f7a1e573fef19255ca3d07c3
Current Contract Checkpoint: 4c749d7cce0f48b5c8146755db43837960e79f4f
Implementation SHA: 153c0d31a699ff15047b6a2e274237497476ec76
Decision: FIX REQUIRED
Task status: FIX REQUIRED
P0 Blockers: NONE FOUND
P1 Blockers: BR-1, BR-3
Historical finding outside current playback scope: BR-2 (FAIL retained; not fixed or PASS)
Slice Required Outcomes all satisfied: NO
Next: Developer corrects BR-1 and completes remaining BR-3 in Task 1.1 under adjusted contract
```

### 审查范围、身份与证据（2026-10-13）

初始工作树为干净 `main`，规划前治理 PASS。已读取必读文档、B 经验、已提交 Slice 与真实 Task Base..Implementation SHA 差异。该范围包含此前获授权的 V4.2 合同／环境提交；另核对 B 接续检查点 `95f52cfb42265d98fde288e9b39756ebddd04885` 至候选的产品增量，不把此前合同变更归为 Developer 自行扩大范围。

报告检查点相对实现候选仅改变 `TASK.md`、`docs/compatibility.md`、`docs/development-environment.md`；可执行源码、测试、工具、SDK 与依赖锁不变。Developer 原始门槛日志已读取，17 项原始证据／产物摘要在 B 重建前核对一致。原始 restore／format 运行作为该候选已有证据保留；B 重建／测试／隔离集成另有独立日志，不能据此把 Task 整体写成 PASS。

B 本机原始证据：`.git/validation-evidence/e005dbdcbd76fe983710721f106a5ccc02eff63f/b-product-review-20261013/INDEX.md`。包含被审查 SHA、全部跟踪输入摘要、Developer 摘要核对、精确命令／退出码／耗时、实际回归日志、隔离输出和独立失败复现。仅本机可读。B 重建使用报告检查点，DLL 摘要与 Developer 候选构建不同，B 构建与部署 DLL 一致；不宣称两次二进制完全相同。运行后记录固定源码、镜像锁、夹具和配置摘要，并披露这些运行输入摘要在恢复后采集。

### 独立验证与可接受的事实

- 治理 PASS；Python 工具回归 30/30 PASS、0 skipped；Release build PASS、0 warnings/errors；C# 现有回归 29/29 PASS、0 skipped；Task Base..Implementation SHA 差异空白检查 PASS。
- 隔离 Jellyfin 集成脚本独立运行 PASS，三次启动插件 Active。首信任／未变化均 0 次匹配编码器调用；同 SHA-1／Size 换 URL 为 1 次，当次和真实重启后均返回新 URL 及 Video/Audio 主流。重启后插件仓库重新首信任，不作为指纹持久化证据。
- 不可达的新 URL 为 HTTP 500、1 次匹配调用；保存的旧流摘要不变；第二次仍为 HTTP 500、1 次调用。夹具恢复且 Jellyfin 地址重新同步，测试实例保持 healthy。
- `allowMediaProbe=false`、禁用／旧 STRM 委托与取消异常的现有单元用例已独立复验。对应真实服务器权限／普通／直播／禁用／手动刷新对照未运行，不能从单元 PASS 推定 AC-2／AC-6 完成。
- 固定源码核对任务注册、进度／取消接口和空默认触发要求；仍是 Slice 3 的接口调研。地址变化请求 1162 ms、随后未变化 39 ms 是本轮单次端到端观测，不能当作 FullRefresh 附带开销的分项测量。

### 当前 Task 的 P1 阻塞项

| ID | 位置／复现与影响 | 同 Task 修正及验收 |
|---|---|---|
| BR-1 | `StrmPlaybackOptimizer.cs:167–183` 把“返回主流＋返回 URL＋内存 ShortcutPath”命名为已保存结果；`ProbeExecutionContext` 只保留是否曾有主流的布尔值。B 独立假对象复现：本次编码器返回 H.264/1920，原生返回仍是旧 MPEG-2/640 主流、地址已变，代码提交新指纹并返回旧流；后续请求 `allowMediaProbe=false` 跳过探测。固定源码中 `FetchShortcutInfo` 先改内存路径，`SaveMediaStreams` 可失败且 `RunCustomProvider` 捕获异常继续刷新，因此该判断没有排除真实保存失败。违反 RO-3／RO-4、AC-4／AC-5 和 REQ-PROBE-002；假对象复现不宣称已注入真实数据库故障。 | 建立与本次结果关联的原生保存成功证据，明确区分媒体流保存和地址持久化；无法证明时保留基线并明确失败／恢复。覆盖本次成功但流保存失败、返回旧流、新地址只在内存更新等分支；随后请求必须重试，不得因误提交跳过。补可核验的隔离原生保存链路证据，不能仅将现有布尔变量改名或检查主流存在。 |
| BR-3 | Task 指定真实对照仍有缺口：普通媒体／直播／旧 STRM／禁用、手动强制刷新、false 权限，以及探测期间 Manifest 再变仅有部分单元证据；FullRefresh 额外提供器工作未作可复现观察。原人为注入取消验证 NOT RUN 保留历史，按 RESCOPE 不再阻塞。其余缺口涉及 AC-2／AC-4／AC-6／AC-7 与 Slice Final 的明示门槛。 | 补当前合同指定的真实对照、实际计数、保存结果和竞态证据；记录 FullRefresh 实际附带工作与限制，不要求另做大规模性能基准。不要求人为注入取消验收；保留原生取消异常处理和已有回归。不得将历史取消 FAIL／NOT RUN 改成 PASS。 |

历史两个行为复现均为 **FAIL**；BR-1 仍阻塞，BR-2 已因 A RESCOPE 退出当前范围，独立 harness 退出 0 仅表示完成复现。原型源码未改，harness 位于证据目录；保留初次运行、一次下一请求检查的 harness 空引用失败及修正后的重跑，未将 harness 错误计为产品失败。

### 历史 BR-2 与 A 取消语义澄清

BR-2 原记录：`StrmPlaybackOptimizer.cs:164–183` 在原生正常返回后没有提交前取消检查。假对象主动取消调用 token 后仍提交指纹，复现 FAIL；前合同曾要求修正。A 最新 RESCOPE 移除了当前播放的该防御性场景，B 不再要求本 Task 修复或真实注入取消验收；原日志、实现 SHA 与结果不变。Slice 2 可取消共享执行须按自己的合同验证该提交边界。以下前次接续说明保留为历史，其取消门槛已被新决定替代。

固定源码 `Jellyfin.Api/Helpers/MediaInfoHelper.cs:148` 的 PlaybackInfo 取源传 `true` 与 `CancellationToken.None`；`StreamingHelpers.cs:129` 的可取消取源传 `false`。当前 PlaybackInfo 探测链不接收客户端取消信号；客户端即使断开连接，也不能据此认定这次原生探测会被取消。不得提高 false 权限。

B 前次把 Slice 的“真实原生探测取消验证”限定为“客户端取消 PlaybackInfo”，该解释过窄。合同没有要求客户端必须取消请求，故撤回仅因该客户端路径不可取消而要求 A 修改合同的升级。Task 1.1 继续，ID、Base、Goal、Scope 和 T4 不变，不新增客户端取消验收义务。

A 已在当前 Contract Checkpoint 明确：客户端退出后，原生执行如果仍实际成功、结果已保存且 Manifest 一致，可以提交；停止播放按 Jellyfin 原生会话／转码行为处理，不新增探测取消关联。仅取消一个共享等待者不阻止仍服务其他等待者的有效执行提交。Developer 旧报告中的“PlaybackInfo 活跃探测取消 BLOCKED／NOT RUN”保留历史事实，但该客户端场景不属于当前合同额外要求，不将其改写为 PASS。

原有取消不覆盖基线的不变量及真实原生取消门槛仍有效：在隔离实例的真实 Jellyfin 原生执行链传入可取消 token，验证实际取消与基线保留，并披露验证入口；不能把私有测试入口的结果宣称为公共 PlaybackInfo 客户端取消。当前该真实验证仍 NOT RUN，BR-2 的独立单元失败仍须修正。如果后续发现原生执行取消验证本身不能满足合同，再按真实阻塞交 A，而不是以客户端请求不可取消代替这一判断。

### Required Outcomes / Surfaces 复核与接续

| Outcome | 当前已取得的事实 | 未完成 |
|---|---|---|
| RO-1 | 固定版本／SDK／包锁，真实 solution、加载／重启、构建证据 | 整体镜像源码溯源限制保持披露；该项证据不代表整体 Task PASS |
| RO-2 | 单一注册／生命周期控制与全接口转发单测，真实跳过／主动探测 | AC-2 原生普通／直播等指定真实对照 |
| RO-3 | 正常成功、不可达失败保流重试；现有单元失败／取消／竞态对照 | BR-1；真实竞态与保存关联；BR-2 退出当前范围 |
| RO-4 | 同 SHA 地址变化的当次／重启新地址与主流 | BR-1 保存成功关联；false 权限／手动刷新真实对照 |
| RO-5 | 版本、接口、原始证据、限制和本次 FIX REQUIRED 结论 | 附带刷新工作的可复现观察；不批准继续 Slice 2／3 |

Required Surfaces 中项目／入口、隔离加载／PlaybackInfo、正常与不可达探测及重启、任务接口调研已有证据；“可重复的可靠指纹提交条件”仍不满足。保留同一 Task 的 ID、Base、Goal、Difficulty 和 T4；Scope／验收与测试计划已按 A RESCOPE 调整；不新建按测试或字段拆分的 Task，不运行 Slice Final，不交 A 最终关闭包。

Developer 应在原 Task 1.1 修正 BR-1 并补调整后的 BR-3 可执行证据，完成修正候选全部 T4 门槛，提交新 SHA 和首次失败／重跑日志，再交 B。A 已修改合同，当前不要求播放链成功返回后的额外取消防御或人为注入取消验收。收尾经验候选：原生提供器会捕获保存异常时，要以本次结果关联及保存边界取证；取消验收先核对真实入口与信号来源，人工注入不能证明正常播放可达。Slice 收尾时再合并到角色经验，当前不记录开发流水账。
