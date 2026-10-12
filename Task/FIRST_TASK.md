# Task 1.1 — 可加载的 Jellyfin 接入原型与三项风险验证

这是首次初始化专用草案，尚未激活。初始化脚本将其写入根 TASK.md，并把下列 DRAFT／占位 SHA 改为 PLANNED／真实激活提交。后续任务使用 Task/TEMPLATE.md，不重复激活本草案。

```text
Task ID: 1.1
Parent Slice: 1
Status: DRAFT
Task Base: {{ACTIVATION_SHA}}
Difficulty: High
Test Level: T4
Planner / Reviewer: B
```

## Goal

在一个固定 Jellyfin 版本上建立可加载的最小原型，完成 Slice 1 的 RO-1～RO-4 技术验证，为 RO-5 提供实证结论。一次验证服务接入、原生探测成功信号和路径持久化，避免在风险未消除前展开完整产品。

## 实际缺口

当前仓库没有 C# 项目，SDK 和目标版本尚未选定，方案示例未经实机验证。读取 compatibility.md，核实实际隔离服务器、对应源码与包依赖后再创建项目。

## 实施范围

- 核实并固定服务器版本／镜像、源码 SHA、目标框架、插件依赖和 SDK；创建真实 solution、插件与测试项目。
- 最小 Plugin／ServiceRegistrator／媒体源包装及完整接口委托，验证实例和释放所有权。
- 用手写版本化 STRM／假或本地媒体服务实现跳过、主动原生探测、同 SHA-1 地址更新的必要原型分支。
- 获取实际 ffprobe 计数与本次成功／失败结果信号，覆盖旧流保留、取消和 Manifest 再变化。
- 用原生持久化验证 ShortcutPath 当次与重启行为。
- 记录构建、加载、对照播放、限制、FullRefresh 附带开销和继续／调整结论。

不得随意更改已提交 SLICE.md 或 Roadmap。实施后由授权事实更新记录证据；新增产品需求返回合同范围判断。

## 验收条件

- [ ] 精确目标版本和依赖形成可构建／可加载原型；启动／关闭正常。
- [ ] 原生实例唯一、无循环依赖、完整委托；普通媒体、直播、旧 STRM、禁用与手动刷新对照正常。
- [ ] 已有主流的版本化 STRM 第二次播放实际 ffprobe 零增量；变化路径实际触发原生探测。
- [ ] 刷新成功、失败保留旧流、取消和版本变化能够区分；找不到可信成功信号时明确报告阻塞。
- [ ] 同 SHA-1 换 URL 当次和重启均正确，原流保留；失败分支不伪报路径更新成功。
- [ ] 原调用 allowMediaProbe=false 的所有路径均不启动探测。
- [ ] 所有记录只用隔离夹具、假数据与脱敏证据；不改生产实例、生成器或代理。
- [ ] 如实完成 T4 必要检查，提交准确实现 SHA；不自行签发 B PASS／A Final Review。

## 必要测试

测试计划修订：按 mediaflow 最新流程显式区分反馈、最终门槛、独立验证和证据。本次只调整执行与记录方式，保留 Task ID／Base／Goal／Scope／验收及 T4 的全部必要门槛；不表示插件已实施或 B 审查已通过。

### 开发／修正反馈

项目创建并固定 SDK 后，补入准确 solution／project 路径和聚焦测试命令。先验证当前改动对应的服务委托、探测结果关联或路径持久化；修正时先重现失败并运行受影响回归。边界变化时运行相关隔离 Jellyfin 链路，不用假对象替代实机证据。

### 最终检查点门槛

项目创建后补入固定 SDK 的 restore、Release build、全部已有 test、相关 format／分析器命令。T4 全部回归用于检验核心服务替换和播放链路的跨模块影响；完整套件已包含的聚焦用例记录覆盖关系，无须机械重复。

治理检查：`python3 scripts/check_governance.py`。提交检查：`git diff --check`。

单独的实机门槛：插件加载与生命周期、全接口委托、普通／直播／旧 STRM／禁用基线；重复播放实际探测计数；主动探测；失败而旧流存在；取消／Manifest 变化；路径更新／保存失败／重启；allowMediaProbe=false。参照 test-matrix.md 的 T01～T04、T08、T17～T19、T21～T24、T26、T28 与 X02、X04、X07，分别关联 Slice 的 AC-1～AC-7。单元全套通过不能替代这些门槛。

### B 独立验证

审查真实 Task Base..Head 和原始日志，在同一隔离版本上独立复现三个关键结果：跳过／主动探测的实际调用计数，失败保留旧流时不会被认作成功，同 SHA-1 换 URL 当次与重启正确。检查原调用 allowMediaProbe=false 的对照。其余构建／回归证据仅在输入匹配且原始产物可读时明确复用；缺失或矛盾时重跑。

### 证据与重跑规则

按开发流程保留候选 SHA、被测内容身份、版本／依赖／夹具摘要、精确命令、实际计数／耗时、原始日志和缺失项，存放于稳定的 `.git/validation-evidence/<source-sha>/<run-id>/` 或 CI 产物。实机日志必须脱敏。

可执行代码、测试、工具、依赖、版本或运行夹具改变后更新相关证据；T4 修正候选完成全部指定最终门槛。纯报告后继提交核对输入未变并重跑治理等文档检查。Slice Final 另行运行当前合同要求。

当前全部产品门槛 NOT RUN；未安装 SDK 或无隔离环境不能算测试通过。是否可以继续由实际风险证据决定，不能跳过核心门槛。

## 非目标

- 完整解析器／所有决策组合、正式 SQLite schema／迁移及通用并发产品实现。
- 配置页、发布包、跨 Jellyfin 版本兼容承诺。
- STRM 生成程序、OpenList API、媒体下载哈希、JellyfinProxy 改造。

## Developer Completion Report

尚未实施。Changed Files、Implemented、Tests and Results、Decisions、Remaining In-Slice Work、Risks / Deviations 均待实证。

```text
Head SHA: NOT SET
```

## B Review Result

```text
Reviewed: NOT SET
Decision: PENDING
Slice Required Outcomes all satisfied: PENDING
Next: PENDING
```
