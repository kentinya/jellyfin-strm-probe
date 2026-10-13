# 仓库开发约束

项目：`Jellyfin.Plugin.StrmProbeOptimizer`，C# Jellyfin 插件。

## 开始工作前

先阅读本文件、[开发流程](docs/development-workflow.md)、根目录 [V4.2 方案](<Jellyfin STRM Probe Optimizer V4.2 开发方案.md>)、[范围说明](docs/scope.md)、[需求](docs/requirements.md)、[用户旅程](docs/product-experience.md)、[架构](docs/architecture.md)、[路线图](docs/roadmap.md)、[SLICE.md](SLICE.md) 和 [TASK.md](TASK.md)。

按当前职责阅读对应经验：[A：Slice 所有者／最终审查](docs/agent-experience/slice-owner-architect-final-reviewer.md)、[B：Task 规划／审查](docs/agent-experience/task-planner-reviewer.md)、[Developer：实施](docs/agent-experience/developer-implementation-role.md)。经验文件只提供方法参考，不改变授权、范围、测试门槛或审查责任。

先检查 `git status --short --branch`，记录已有改动。实施任务前运行 `python3 scripts/check_governance.py`。尚未初始化 Git 时只能用 `--bootstrap` 检查规划，不能据此开始未激活的产品 Task。

用户在会话中明确给出的范围和授权优先于仓库指南。本次已授权按最新 V4.2 方案重规划相关文档；不据此开始插件实施。

## 文档职责

1. 本文件维护长期业务、架构和范围约束。
2. `docs/development-workflow.md` 独立维护 Slice／Task 状态、Git、测试和审查流程。
3. V4.2 是当前开发基准，保留用户提供的原文；V3.0 从工作区移除后仍可从 Git 历史读取。`docs/scope.md` 记录版本替代与生成程序排除边界。
4. `docs/requirements.md` 是本次插件开发的稳定需求规范；`docs/product-experience.md` 定义用户结果。原方案作为保留的输入参考，不把其中被排除的生成程序重新纳入范围。
5. `docs/architecture.md` 明确区分已经实现与目标设计。
6. `SLICE.md` 限定当前完整能力，活动 `TASK.md` 限定其中的实施单元。
7. `docs/agent-experience/` 保存可复用的角色经验，不保存 Task 历史或验收结论。

下层文件只能细化范围，不能偷偷弱化业务规则。总体方案不是一次实现全部产品的授权。

## 不可弱化的业务规则

- 优化只作用于受支持的版本化 STRM；普通媒体、禁用插件和旧 STRM 默认委托 Jellyfin 原生处理。
- 没有必要主媒体流时要求探测；原调用 `allowMediaProbe=false` 永远不能被改为允许探测。
- SHA-1 只有新旧两侧均为有效的 40 位十六进制内容哈希时才能比较。
- URL 不变时，有效 SHA-1 相同则忽略 Size 差异；有效 SHA-1 不同则要求探测。
- URL 改变一律要求探测，包括有效 SHA-1 相同、Size 相同的情况；URL 判断先于 SHA-1／Size。
- URL 不变且 SHA-1 无法比较时，只在新旧有效 Size 不同时要求探测；信息不足记录限制，不凭空认定变化。
- 修改时间本身不能触发探测；不能用 URL 的哈希冒充媒体内容 SHA-1。
- URL 改变后由经验证的原生探测／刷新流程更新并持久化播放地址与有效媒体流；当次 PlaybackInfo 和重启后使用新地址，不保留仅更新路径的优化分支。
- 首次接管默认信任已有主媒体流并建立历史指纹，不能引起全库重探测；信任接管不宣称本次实测成功。
- 除首次信任接管外，新指纹只能在本次原生探测确实成功、结果已持久化且 STRM 未再变化后提交。
- 失败、取消、解析错误和探测期间变化不覆盖可信基线。历史有效 SHA-1 保留身份关联，不能套用到另一个已确认版本。
- 播放沿用目标 Jellyfin 的原生取消语义：当前固定版本 PlaybackInfo 传 CancellationToken.None，客户端退出不取消已启动的探测，不据此阻止有效成功指纹提交；原生抛出取消异常时仍保留旧基线并传播异常；当前播放原型不要求成功返回后额外检查取消或人为注入取消验收。批量／共享执行的取消提交保护与实机验证在 Slice 2／3 按原生任务与协调器规则处理，不新增客户端停止播放到探测取消的关联。
- 同一项目／媒体源共享正在执行的探测；不同媒体源独立，取消单个等待者不应错误取消其他人的工作。
- 播放与批量任务共用决策、指纹提交和 ProbeCoordinator；插件主动探测全局并发默认 2、可设 1～8，不限制 Jellyfin 或其他插件独立发起的探测。
- 批量检查分页读取所选媒体库并按需探测；由 Jellyfin 原生计划任务负责手动运行、停止、定时和进度，默认无自动触发时间。
- 手动强制刷新保留 Jellyfin 原生行为，不凭“媒体已更新”事件直接确认新版本。

## 架构与输入边界

- STRM 生成程序明确排除；插件只读取 STRM，不能写入、移动或删除它。
- 插件不调用 OpenList 元数据 API，不下载媒体计算 SHA-1，不改写 JellyfinProxy。
- 媒体流保存在 Jellyfin 原生库；插件 SQLite 仅保存按项目／媒体源关联的最小历史指纹，不保存完整 PlaybackInfo，也不维护持久化探测状态机。
- 不增加独立调度系统、独立运行按钮、ProbeState／PendingProbe／ProbeFailed 或 ShortcutPathSynchronizer；首版不接 ILibraryPostScanTask。
- 解析器、决策器不进行网络、数据库或 Jellyfin 刷新操作；版本适配与原生刷新集中在接入层。
- 使用 Jellyfin 已有探测能力；不自行安装或打包另一套 FFmpeg／ffprobe。
- 核心 DI 替换、原生探测成功信号和路径持久化必须先实证；未经验证不能宣传兼容或继续铺开后续实现。
- 运行时插件状态库异常时停止优化并尽可能委托原生行为；启动时核心注册失败不能承诺一定自动回退。

## 用户结果与证据

播放正确性优先：跳过探测同时仍须返回正确 URL、可用主媒体流和明确失败／恢复路径。配置页面不得把固定规则做成可关闭的开关；日志不能泄露完整签名 URL、token、Cookie 或私有路径。

单元测试、真实 Jellyfin 集成和外部代理联调分别报告。`NOT RUN`、`BLOCKED`、`SKIPPED` 不能写成 PASS。通过文件治理检查不意味着插件构建、探测或播放已通过。

## 工作方式

角色与审查责任见开发流程。角色名称不自动授权启动其他代理；只有用户或适用指令明确要求时才进行代理委派。

已授权 Task 内的实现、必要修复、隔离测试与普通本地提交持续进行，无须重复询问。保留所有无关用户改动；不自动推送，不重写历史，不做破坏性清理，不改生产媒体或运行中的 Jellyfin。只读 Git 边界不能绕过。
