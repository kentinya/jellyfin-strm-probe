# 兼容性与接入验证

## 当前结论

兼容性只声明已经实测的组合和入口；当前验收状态、候选审查和未运行范围见 [Slice 合同](../SLICE.md)、[Task](../TASK.md)、[测试矩阵](test-matrix.md) 与 [关闭账本](progress.md)。固定组合为 Jellyfin／Controller／Model `12.2.0`、`net10.0`、SDK `10.0.401`、Linux x64；不据此承诺跨版本或全格式兼容。播放与批量沿用原生取消语义，只共享已实际开始的探测。

MP4／MKV视频在原生Web入口的八类决策、缺Video、ColorRange三阶段往返、失败与同目标恢复及重启先读已有[Slice 5分层证据](progress.md#slice-5-closed)。该固定版本原生MediaStreamRepository双向Map遗漏ColorRange；插件仍精确关联编码器与成功保存，仅对重读null作有界匹配，不接受其他字段／源冲突或保存失败。证据不构成跨版本适配或音频STRM支持；本页下方早期Slice的未验证事实按其当时范围保留。

下表是早期源码定位候选；当前固定组合的加载／运行事实以上文及关闭证据为准。

| 候选源码 | 已记录标签提交 | 定位用途 |
|---|---|---|
| Jellyfin v10.11.8 | `2c62d40f0d13926874eef9118a95be0dcee4e659` | 旧规划候选；此前读取 global.json 为 SDK 9.0.0／latestMinor，仍需目标框架与包核实 |
| Jellyfin v12.2 | `ca0f16eb7c195f720a1493ed469a27c4657db0c6` | V4.2 最初调研候选；后续固定为当前实测组合，单版本包范围见下文 |

先固定一个隔离服务器版本／镜像 digest、相应源码 SHA、框架、依赖和 SDK，再构建。不能由两组标签推定一个插件包兼容两版。

## Task 1.1 源码定位（2026-10-13）

官方发布页将 v12.2 标为最新稳定版本；发布提交为 `ca0f16eb7c195f720a1493ed469a27c4657db0c6`。本轮网页核对到：

- [`MediaSourceManager.GetPlaybackMediaSources`](https://github.com/jellyfin/jellyfin/blob/ca0f16eb7c195f720a1493ed469a27c4657db0c6/Emby.Server.Implementations/Library/MediaSourceManager.cs#L177-L198) 在 `allowMediaProbe` 为 true 且项目为 `.strm` 时会调用 `RefreshMetadata`，设置 `EnableRemoteContentProbe=true` 和 `FullRefresh`，再重新读取静态媒体源；缺主视频／音频流也会进入该刷新分支。源码定位确认原生播放接入候选，但不能证明包装 DI、单例所有权、实际探测计数或失败语义。
- [`ProbeProvider.FetchVideoInfo`](https://github.com/jellyfin/jellyfin/blob/ca0f16eb7c195f720a1493ed469a27c4657db0c6/MediaBrowser.Providers/MediaInfo/ProbeProvider.cs#L234-L332) 对可探测视频 STRM 调用 `ProbeVideo`，并由原生 Provider 从 STRM 读取远程地址。该源码路径仍不能替代本次结果、持久化主流和地址的实机关联验证。
- [`MediaBrowser.Controller.csproj`](https://github.com/jellyfin/jellyfin/blob/ca0f16eb7c195f720a1493ed469a27c4657db0c6/MediaBrowser.Controller/MediaBrowser.Controller.csproj#L36) 目标框架为 `net10.0`。源码定位阶段尚未固定 SDK、镜像、依赖或可加载插件；后续 Task 1.1 的固定组合与原型加载证据见下节。

先前执行环境缺少 SDK／可用 Docker daemon 的记录保留在 [Task 1.1 历史交接](progress.md#slice-1-closed) 及 [环境交接](development-environment.md)；阻塞已解除，真实插件构建和隔离加载证据见下节。

已对固定源码 `ca0f16eb7c195f720a1493ed469a27c4657db0c6` 检查 `MediaSourceManager`、Provider、`MediaInfoHelper`、任务模型与任务调度代码。源码定位是接口证据，不替代插件行为验收。

## 播放与批量取消语义

以下限定固定 Jellyfin `12.2.0`／源码 `ca0f16eb7c195f720a1493ed469a27c4657db0c6`，版本变化后重新核对。A 的 Slice 1 实质范围调整保留于 [关闭快照](progress.md#slice-1-closed)，历史 [Slice 2 合同修订记录](progress.md#slice-2-closed) 按用户要求替代人为可取消执行义务；没有将源码存在或未运行场景改为实机 PASS。

| 入口／动作 | 固定源码行为 | 插件与验收边界 |
|---|---|---|
| PlaybackInfo 取源 | [`MediaInfoHelper`](https://github.com/jellyfin/jellyfin/blob/ca0f16eb7c195f720a1493ed469a27c4657db0c6/Jellyfin.Api/Helpers/MediaInfoHelper.cs#L148) 传 `true` 和 `CancellationToken.None` | 是否探测由媒体状态与插件决策决定；客户端退出不沿此入口取消探测，不要求客户端取消实机场景 |
| 实际流请求取源 | [`StreamingHelpers`](https://github.com/jellyfin/jellyfin/blob/ca0f16eb7c195f720a1493ed469a27c4657db0c6/Jellyfin.Api/Helpers/StreamingHelpers.cs#L129) 传调用 token 和 `allowMediaProbe=false` | 原样保留权限，不为测试取消而升级为允许探测 |
| 报告停止播放 | [`PlaystateController`](https://github.com/jellyfin/jellyfin/blob/ca0f16eb7c195f720a1493ed469a27c4657db0c6/Jellyfin.Api/Controllers/PlaystateController.cs#L249) 停止关联转码并更新会话 | 该处理不向先前 PlaybackInfo 探测传取消 token；插件不新增停止事件到探测的关联 |
| 停止计划任务 | [`ScheduledTasksController`](https://github.com/jellyfin/jellyfin/blob/ca0f16eb7c195f720a1493ed469a27c4657db0c6/Jellyfin.Api/Controllers/ScheduledTasksController.cs#L122) 调用任务取消；[`ScheduledTaskWorker`](https://github.com/jellyfin/jellyfin/blob/ca0f16eb7c195f720a1493ed469a27c4657db0c6/Emby.Server.Implementations/ScheduledTasks/ScheduledTaskWorker.cs#L331) 把自身 token 传入执行并在停止时取消 | Slice 3 已将该 token 仅用于候选获取边界／后续批次／未实际开始工作；已开始探测继续完成，停止收尾等待结果结算，不能向其传入任务停止信号 |

客户端退出不等于执行取消。本次原生探测继续成功、结果已保存且 Manifest 一致时，仍可按全部提交条件接受指纹。原生执行自身抛出取消异常时保留旧基线；批量停止或等待者退出不取消任何已开始探测，也不阻止满足全部成功条件的提交，即使已经没有其他等待者。

Slice 1 不再要求人为传入可取消 token 的真实原生取消验证，也不要求原生成功返回后的额外取消检查；原调用 token／权限与原生取消异常处理保留。旧注入取消 NOT RUN 和假对象 FAIL 记录未改为 PASS，仅退出当前门槛。本次用户明确停止／共享规则后，Slice 2 改为验证只共享已开始探测、排队不共享及正常收尾，移除人为执行取消源和探测中／提交前取消实机门槛；Slice 3 验证批量仅撤销未开始工作及已开始探测结算。更换版本、入口或取消语义后重新核对合同，不改写旧结果。

## Task 1.1 原型实测（2026-10-13）

测试输入为隔离临时库的手写版本化 STRM、两个字节完全相同的本地合成 MP4、隔离 Jellyfin `12.2.0` 与本地媒体服务。STRM 临时写入该媒体字节的实际 SHA-1 和 Size；换 URL 场景保留两者不变。运行脚本在结束时恢复原 STRM，并重新通过 Jellyfin 同步原地址。

- 固定组合：SDK `10.0.401`、目标 `net10.0`、Jellyfin.Controller／Model `12.2.0`、源码 SHA `ca0f16eb7c195f720a1493ed469a27c4657db0c6`。服务器和本地媒体服务镜像 digest 见 [开发环境固定输入](development-environment.md#已运行环境证据)。
- 插件在三次隔离容器启动后均为 Active。首次信任接管、未变化播放及地址变化后的未变化播放分别记录 0、0、0 次匹配原生编码器探测，返回必要 Video／Audio 主流。
- 同 SHA-1／Size 的 URL 改变记录 1 次匹配原生 `IMediaEncoder.GetMediaInfo` 调用，结果含 Video／Audio 主流；PlaybackInfo 返回新 URL（证据仅记录 SHA-256），之后容器重启仍返回新 URL／主流，且没有新探测。
- 不存在的新 URL 返回 HTTP 500，不被当成成功；同一失败 URL 的第二次 PlaybackInfo 再记录 1 次探测。控制逻辑与单元测试验证旧指纹未被失败结果替代。
- `IMediaSourceManager` 全接口委托与通用单例释放有单元回归，四个核心服务注册已由固定源码与实际接入审查核对；隔离实例实测普通媒体、旧 STRM、Live TV、插件禁用后原生播放及重新启用。各路径均返回有效媒体源且未产生插件 STRM 优化事件。
- 对修改后 STRM 的实际 `/Videos/{itemId}/stream?static=true` 请求返回 HTTP 200 与 20,995 字节，没有插件探测事件；后续 PlaybackInfo 对同一变化 URL 执行 1 次匹配探测。这是真实 `allowMediaProbe=false` 流入口验证。公共 PlaybackInfo 固定传 `true`，因此未伪造 PlaybackInfo 的 false 参数调用。
- 竞态用隔离媒体服务的延迟 URL：确认探测已开始后修改 STRM，PlaybackInfo 返回 HTTP 500，日志记录 1 次匹配调用及保留指纹；修复后的当前 Manifest 随后以 1 次探测成功恢复。
- 手动 FullRefresh 返回 HTTP 204，保存后条目 ETag 改变；该项手动刷新未产生本地媒体 GET 或进程级 `GetMediaInfo` 调用，后续变化地址的 PlaybackInfo 仍执行 1 次探测。三次同 SHA-1／Size 地址切换的 PlaybackInfo 原生刷新均记录 1 次匹配调用和 1 次合成媒体 GET；其中两次重复运行还分别由进程级计数观察到 1 次 `GetMediaInfo`。调用时间、原始计数及限制见候选证据索引；这是固定合成夹具的调用路径观察，不是通用性能基准。

目标版本任务接口已从固定源码核实：`IScheduledTask.ExecuteAsync(IProgress<double>, CancellationToken)` 提供取消与百分比进度；`GetDefaultTriggers()` 提供默认触发；`IConfigurableScheduledTask` 暴露隐藏、启用和日志设置。`ApplicationHost.RunStartupTasksAsync` 通过 `GetExports<IScheduledTask>(false)` 添加任务，`TaskManager` 建立 Worker；`ScheduledTasksController` 提供管理员手动运行、停止和触发器配置。Worker 读取已有触发器配置，否则使用 `GetDefaultTriggers()`；若该方法抛出异常会回退到每日触发，因此无自动时间要求必须正常返回空序列，不能抛异常。该次接口研究没有实现或运行本插件任务；后续 Slice 3 已通过真实任务验收。

B 另在隔离实例临时开启 Debug，两次地址变化都观察到 `ProbeProvider`、`MovieNfoProvider`、`TrickplayProvider` 各调用一次，ETag 改变，匹配探测和合成媒体 GET 各一次，PlaybackInfo 为 91／75 ms。日志级别与 STRM 已恢复。提供器调用不证明远程下载／Trickplay 生成，不提供开销分项或生产性能承诺；原始脱敏证据见 Closure Packet 引用的 B 索引。

上述为有限核心原型及独立 Slice Final 证据，A 已据此关闭 Slice 1；在该历史关闭时，发布包、多版本／广泛媒体兼容和外部代理联调仍未验证。后续接受事实按下文、[测试矩阵](test-matrix.md) 与 [关闭账本](progress.md) 区分。

## Slice 1 风险门槛

A 环境准备及 Task 1.1 原型后续：SDK、固定源码、镜像 digest、隔离服务、本地媒体链路和真实插件 PlaybackInfo 均已有分项证据。下表为 B 核对且经 A 最终审查接受的原型门槛事实。官方镜像没有 revision 标签，镜像整体源码构建溯源仍有限；NuGet nuspec repository commit 已与固定源码 SHA 核对一致。

| 问题 | 必须取得的证据 | 状态 |
|---|---|---|
| 核心 DI 接入 | 注册顺序、单一原生实例、无循环依赖、释放所有权、全接口委托、启动／关闭、普通媒体／直播 | PASS；接口／通用生命周期回归、固定注册与隔离对照已独立核对 |
| 跳过重复探测 | 未变化且已有主流的版本化 STRM 二次播放 ffprobe 零增量，原生媒体源有效 | B 隔离复现 0 匹配调用及有效主流；该正常分支 PASS |
| 主动原生探测 | 变化时实际执行，包含 URL 改变且 SHA-1 相同；不靠 true 参数猜测 | B 复现同 SHA-1／Size URL 变化 1 次匹配调用；该正常分支 PASS |
| 成功与指纹提交 | 真成功、故意失败而保留旧流、Manifest 再变的对照；新结果已保存后才提交；原生取消异常保留基线 | PASS；独立保存失败 harness、原生事务定位、成功保存及真实失败／竞态／恢复 |
| 地址／流持久化 | URL 改变后原生探测并保存，当次 PlaybackInfo 新地址，重启仍有效且有必要主流；保存失败明确 | PASS；当次／重启保存与失败保流重试已独立复验；内部数据库故障未注入 |
| 探测权限／禁用 | allowMediaProbe=false 各分支不执行；禁用／旧 STRM／手动刷新原生对照 | PASS；真实 false 流入口、禁用、旧 STRM、手动 FullRefresh 已独立复验；公共 PlaybackInfo 不提供 false 参数 |

历史原型的接入事实和限制见 [关闭账本](progress.md)；逐项用例与未运行边界见 [测试矩阵](test-matrix.md)。这些历史证据不扩展为跨版本、外部代理或全格式支持声明；测试使用目标 Jellyfin 已有 FFmpeg／ffprobe。

## 已接受的播放与共享验证边界

Slice 2 关闭时已验证 SQLite 指纹的真实重启／失败恢复、多源身份、实际开始后的共享及代表性全局并发计数；正常收尾、结束重查及行动前重判有确定性回归。公共 PlaybackInfo 仍传 None，不增加人为执行取消入口；该次未运行的逐分支实机保留历史 NOT RUN，后续视频矩阵证据见本页[当前结论](#当前结论)和测试矩阵，不倒写旧结果。

## 单版本安装包（Slice 4 RO-1）

仓库内 `scripts/package_plugin.py` 从固定 Release 输出与已锁依赖生成 Linux x64 ZIP、清单与 SHA-256；`scripts/run_isolated_package_integration.py` 在专用隔离实例（独立 Compose project、端口与工作区）仅用归档完成安装验收。负载包含插件程序集、依赖清单、托管与 Linux x64 native SQLite 依赖、`meta.json` 与第三方许可，不含 Jellyfin 核心库、FFmpeg、其他平台 runtime、SDK、源码或凭据。

已验证事实（Task 4.1 已由 B 独立 PASS，审查快照 `0e7b26b381ed5f71781e75d317275afa51d791e9:TASK.md`）：干净实例仅解包安装后插件 Active，进程加载负载摘要与归档一致；原生 SQLite 创建／读写／重启恢复；真实配置页五项保存与重启读回；原生任务唯一且默认无触发；MP4（H.264／AAC）与 MKV（H.264／AAC）在原生 Web 客户端实际播放（视频时间与解码画面推进）；首次已有主流信任零插件探测、未变复查零探测、同 SHA-1／Size 换 URL 后实际探测并持久化、重启后复用；从 Slice 3 接受构建 `7c64eb5dcad6e5f20fb7eb41819be2521f65484d` 替换保留配置与可信指纹并重检未完成变化；禁用／移除后原生播放、重装后重新检查；损坏／缺 native／GUID／ABI 不符／越界路径／符号链接归档在部署前被拒绝且不损伤有效安装。

本项只证明固定 Jellyfin `12.2.0`／Linux x64 的安装包路径，不是跨版本、跨平台或全格式兼容声明；其他 Slice 4 门槛不由该包验证。

## Slice 4 大库／扫描与证据边界

大库工具支持 --reuse-workspace，在明确归属的新副本复用现存全部 1004 项原生索引／主流；至少 1000 是下限，不截取数量、不重新建库／准备全库。all 覆盖首次信任、未变、增量、查询中停止、探测停止收尾／恢复与重启选源；focused 为 PARTIAL，不冒充完整验收。命令及前提见 [测试矩阵](test-matrix.md#slice-4-大库验收本地运行)。

Task 4.2／RO-3 与 Task 4.3／RO-2 已获 B PASS，准确实现／审查快照统一见 [Slice 4 关闭记录](progress.md#slice-4-closed)。4.3 最终完整报告、早期 PARTIAL／失败、工具修正和 B 原始证据索引保留于 `57c5072db0cebf4bcf5fa64c3cde635e9a23dcb3:TASK.md`；既有 plugin／batch 完整门禁包含已披露的私有异步夹具准备适配，不声称未经适配命令通过。准备库、基线与失败副本继续保留。

Slice 4 当时最终候选的完整门禁复用、新增三阶段重启补证及全部限制见 [Closure Packet](progress.md#slice-4-closed)，A 的接受范围与独立核验见 [A Final Review](progress.md#slice-4-closed)；后续候选的匹配回归见 [Slice 5 关闭记录](progress.md#slice-5-closed)。本地单版本 ZIP、真实大库与完整扫描的分层证据不扩展为其他 Jellyfin／平台、通用性能 SLA 或全格式兼容。完整阶段比对覆盖五字段、当前项目／源身份、原生地址和必要主流，先于重启后 PlaybackInfo 取源，避免以播放修复替代持久化证明。

## JellyfinProxy 与 OpenList 未验证

2026-10-20 用户明确授权不验证 JellyfinProxy，原 RO-4／AC-7 及代理专属构建、依赖／镜像固定、缓存、302／GET／Range 与代理客户端内容验收已撤出当前交付范围。状态为历史 NOT RUN、按用户授权不执行，不记 PASS、不宣称任何代理版本兼容；旧计划固定源码与缓存风险仅为只读摸底，不是实际运行或已确认缺陷。原 4.4 完整计划见 `4cc02048fb50c3c0b50a1b1b116246b202d86aaf:TASK.md`。

原生 PlaybackInfo／MediaSourceId→URL／必要主流、换地址后的首次／重启、失败恢复、多版本选源与 MP4／MKV 原生 Web 实际播放义务不变；不能因代理排除而漏验或降低原生正确性。插件不改代理代码／缓存、不调用 OpenList 元数据 API；真实 OpenList 专有 API／鉴权仍 NOT RUN，不宣称 OpenList 联调通过。每个交付包只声明实际验证范围，核心 API／DI 变更后重新实证。
