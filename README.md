# Jellyfin STRM Probe Optimizer

按版本化 STRM 的 URL、内容 SHA-1 和字节 Size 判断是否需要 Jellyfin 原生探测。V4.2 采用播放自动检查、Jellyfin 原生批量计划任务和共享并发控制；URL 改变一律要求探测。

项目：`Jellyfin.Plugin.StrmProbeOptimizer`，C# 插件。SQLite 仅保存最小历史指纹，媒体流继续保存在 Jellyfin 原生库，不维护独立探测状态机。

**Slice 1 核心原型已由 A 最终审查 PASS / CLOSED，完整产品尚未交付。** [最终审查](docs/progress.md#slice-1-closed) 与 [Closure Packet](docs/progress.md#slice-1-closed) 记录构建、加载、探测／保存、失败恢复和重启证据。固定 SDK `10.0.401`、Jellyfin `12.2.0`、源码／依赖与镜像 digest 见 [开发环境](docs/development-environment.md)。[Slice 2](SLICE.md) 的 Task 2.1／2.2 已经 B 独立审查 PASS，完成 SQLite／稳定多源播放闭环、实际开始后的探测共享、全局并发和核心配置；[核心配置操作说明](docs/core-configuration.md) 提供操作与恢复方法。已停止创建 Task，单独 Slice Final 全部通过，Closure Packet 已提交给 A；A 最终审查尚未运行。完整配置页、批量任务、发布包和外部代理联调仍延期。

## 开发基准与范围

[V4.2 原始方案](<Jellyfin STRM Probe Optimizer V4.2 开发方案.md>) 是当前基准。V3.0 已按用户改动从工作区移除，原文及旧合同可在 Git 检查点 `4b1d0468c1e43e6e9034ef98e99b6cc44ea59485` 中读取；不改写历史。

**不开发 STRM 生成程序。** 插件只读现有 STRM，不调用 OpenList 元数据 API、不下载媒体计算哈希、不改写 JellyfinProxy。首版不开发独立调度器、独立任务按钮、仅更新路径服务或扫描后自动触发，见 [范围说明](docs/scope.md)。

## 从这里开始

1. 阅读 [AGENTS.md](AGENTS.md)、[开发流程](docs/development-workflow.md) 和 V4.2 方案。
2. 阅读 [需求](docs/requirements.md)、[用户旅程](docs/product-experience.md)、[架构](docs/architecture.md) 与 [测试矩阵](docs/test-matrix.md)。
3. 查看 [当前 Slice](SLICE.md)、[当前 Task](TASK.md)、[四个 Slice 路线图](docs/roadmap.md) 和 [进度](docs/progress.md)。
4. 开发环境执行 `python3 scripts/development_environment.py doctor`；安装与隔离运行见 [环境交接](docs/development-environment.md)。

Slice 1 已证明固定版本上的核心接入、可靠原生成功信号与最新地址持久化。Slice 2 已由 B 接受全部 Required Outcomes／Surfaces，当前无活动实施 Task，单独 Slice Final 通过且已提交 Closure Packet 给 A；详细计划／报告／独立审查与本机证据见 [进度](docs/progress.md#当前开发指针)。Slice 2 尚未由 A 关闭，Slice 3／4 保持 PLANNED。

## 产品目标

- 未变化且有主媒体流时复用；URL 不变且 SHA-1 相同忽略 Size，SHA-1 不可比时比较有效 Size；Modified 不参与。
- URL 改变始终探测，成功后使用并保存新地址；allowMediaProbe=false 不被提高权限。
- 首次默认信任已有主流；变化指纹只在本次原生探测成功、结果已保存且 STRM 未再变后提交。失败保留旧指纹，下次重新比较。
- 「控制台 → 计划任务 → STRM 媒体信息检查」支持原生运行／停止／定时，默认无自动触发；分页只处理需要探测的项目。停止只撤销未开始工作，已开始探测继续完成并按条件提交，收尾报告实际结果。
- 播放与批量共用 ProbeCoordinator，只共享已实际开始且仍在执行的探测，排队不共享；插件主动探测并发默认 2、允许 1～8，不限制其他原生任务或插件。

上列描述完整产品目标；当前已接受的播放／指纹／共享和核心配置范围见 Slice 2，原生批量与后续发布仍未交付。兼容性及接口定位见 [compatibility.md](docs/compatibility.md) 和 [references.md](docs/references.md)。

## 仓库检查

```bash
git status --short --branch
python3 scripts/check_governance.py
python3 -m unittest discover -s tests -v
git diff --check
```

治理与 Python 回归只验证文档文件身份、已提交合同及状态约束，不代表插件构建、探测、播放或独立审查通过。

`scripts/bootstrap_repository.py` 与 `bootstrap-manifest.json` 是 V3.0 首次初始化历史，当前已初始化仓库不得重新运行，也不重生成旧清单。当前治理使用 V4.2 原文身份及维护中的文件清单；需要追溯旧初始化时读取 Git 历史。
