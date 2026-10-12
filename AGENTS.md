# 仓库开发约束

项目：`Jellyfin.Plugin.StrmProbeOptimizer`，C# Jellyfin 插件。

## 开始工作前

先阅读本文件、[开发流程](docs/development-workflow.md)、根目录 V3.0 方案、[范围说明](docs/scope.md)、[需求](docs/requirements.md)、[用户旅程](docs/product-experience.md)、[架构](docs/architecture.md)、[路线图](docs/roadmap.md)、[SLICE.md](SLICE.md) 和 [TASK.md](TASK.md)。

按当前职责阅读对应经验：[A：Slice 所有者／最终审查](docs/agent-experience/slice-owner-architect-final-reviewer.md)、[B：Task 规划／审查](docs/agent-experience/task-planner-reviewer.md)、[Developer：实施](docs/agent-experience/developer-implementation-role.md)。经验文件只提供方法参考，不改变授权、范围、测试门槛或审查责任。

先检查 `git status --short --branch`，记录已有改动。实施任务前运行 `python3 scripts/check_governance.py`。尚未初始化 Git 时只能用 `--bootstrap` 检查规划，不能据此开始未激活的产品 Task。

用户在会话中明确给出的范围和授权优先于仓库指南。本次生成开发基线文件的工作已经获授权；这里的实施合同用于后续插件开发。

## 文档职责

1. 本文件维护长期业务、架构和范围约束。
2. `docs/development-workflow.md` 独立维护 Slice／Task 状态、Git、测试和审查流程。
3. V3.0 原方案保留原文；`docs/scope.md` 记录本次明确排除的生成程序部分。
4. `docs/requirements.md` 是本次插件开发的稳定需求规范；`docs/product-experience.md` 定义用户结果。原方案作为保留的输入参考，不把其中被排除的生成程序重新纳入范围。
5. `docs/architecture.md` 明确区分已经实现与目标设计。
6. `SLICE.md` 限定当前完整能力，活动 `TASK.md` 限定其中的实施单元。
7. `docs/agent-experience/` 保存可复用的角色经验，不保存 Task 历史或验收结论。

下层文件只能细化范围，不能偷偷弱化业务规则。总体方案不是一次实现全部产品的授权。

## 不可弱化的业务规则

- 优化只作用于受支持的版本化 STRM；普通媒体、禁用插件和旧 STRM 默认委托 Jellyfin 原生处理。
- 没有必要主媒体流时要求探测；原调用 `allowMediaProbe=false` 永远不能被改为允许探测。
- SHA-1 只有新旧两侧均为有效的 40 位十六进制内容哈希时才能比较。
- 有效 SHA-1 相同时忽略 Size 差异；SHA-1 不同时要求探测。
- URL 改变且无法比较 SHA-1 时要求探测，即使 Size 相同。
- URL 不变且 SHA-1 无法比较时，只在新旧有效 Size 不同时要求探测；信息不足记录限制，不凭空认定变化。
- 修改时间本身不能触发探测；不能用 URL 的哈希冒充媒体内容 SHA-1。
- URL 改变且内容相同时，必须同步并持久化 `ShortcutPath`，让当次 PlaybackInfo 使用新地址，且保持已有媒体流。
- 首次接管默认信任已有主媒体流并建立 `Assumed`，不能引起全库重探测。
- 只有可关联到本次实际成功探测、已持久化且 STRM 未再变化的结果，才能提交 `Verified`。
- 失败、取消、解析错误和探测期间变化不覆盖可信基线。历史有效 SHA-1 保留身份关联，不能套用到另一个已确认版本。
- 同一项目／媒体源共享正在执行的探测；不同媒体源独立，取消单个等待者不应错误取消其他人的工作。
- 手动强制刷新保留 Jellyfin 原生行为，不凭“媒体已更新”事件直接确认新版本。

## 架构与输入边界

- STRM 生成程序明确排除；插件只读取 STRM，不能写入、移动或删除它。
- 插件不调用 OpenList 元数据 API，不下载媒体计算 SHA-1，不改写 JellyfinProxy。
- 媒体流保存在 Jellyfin 原生库；插件 SQLite 仅保存观测、确认基线和探测状态，不缓存完整 PlaybackInfo。
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
