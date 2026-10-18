# Jellyfin STRM Probe Optimizer

按版本化 STRM 的 URL、内容 SHA-1 和字节 Size 判断是否需要 Jellyfin 原生探测。V4.3 采用播放自动检查、Jellyfin 原生批量计划任务和共享并发控制；URL 改变一律要求探测。

项目：`Jellyfin.Plugin.StrmProbeOptimizer`，C# 插件。SQLite 仅保存最小历史指纹，媒体流继续保存在 Jellyfin 原生库，不维护独立探测状态机。

**Slice 1／2／3 已由 A 最终审查 PASS / CLOSED，完整产品尚未交付。** [Slice 3 最终审查快照](docs/progress.md#slice-3-closed) 接受完整配置页、所选库按需批量检查、原生运行／停止／定时、播放混合共享及准确故障反馈；[关闭账本](docs/progress.md#slice-3-closed) 保留范围与分层证据。固定 SDK `10.0.401`、Jellyfin `12.2.0`、源码／依赖与镜像 digest 见 [开发环境](docs/development-environment.md)。操作与恢复见 [配置说明](docs/core-configuration.md)。[Slice 4](SLICE.md) 已 ACTIVE，承接真实 3000 项媒体库／完整扫描、实际代理播放链及固定 Jellyfin／Linux x64 安装包与恢复；RO-1 安装包已由 B 独立 PASS，RO-3 完整扫描重叠已由 B 独立 PASS，RO-2／RO-4 仍 NOT RUN，当前为 Task 4.3 真实 3000 项媒体库计划。

## 开发基准与范围

[V4.3 方案](<Jellyfin STRM Probe Optimizer V4.3 开发方案.md>) 是当前基准，仅修订 V4.2 的扫描方式；V4.2 原文保留在 Git 历史。V3.0 已按用户改动从工作区移除，原文及旧合同可在 Git 检查点 `4b1d0468c1e43e6e9034ef98e99b6cc44ea59485` 中读取；不改写历史。

**不开发 STRM 生成程序。** 插件只读现有 STRM，不调用 OpenList 元数据 API、不下载媒体计算哈希、不改写 JellyfinProxy。首版不开发独立调度器、独立任务按钮、仅更新路径服务或扫描后自动触发，见 [范围说明](docs/scope.md)。

## 从这里开始

1. 阅读 [AGENTS.md](AGENTS.md)、[开发流程](docs/development-workflow.md) 和 V4.3 方案。
2. 阅读 [需求](docs/requirements.md)、[用户旅程](docs/product-experience.md)、[架构](docs/architecture.md) 与 [测试矩阵](docs/test-matrix.md)。
3. 查看 [当前 Slice](SLICE.md)、[当前 Task](TASK.md)、[四个 Slice 路线图](docs/roadmap.md) 和 [进度](docs/progress.md)。
4. 新服务器按 [可迁移开发环境](docs/development-environment.md) 准备 SDK、[公开镜像锁](dev/images.lock.json) 和隔离实例，再运行 doctor。任意检出路径均可继续当前 Task；旧服务器资源、容器、账户和本机证据目录不再是开工前提。单版本安装包、配置与恢复见 [安装包说明](docs/package-installation.md)。

Slice 4 Base 固定为 Slice 3 关闭提交 `03169b07d110964562f7da31d2c3d7add82e5ff5`，合同 Implementation Head 仍为 NOT SET；最新经 A 接受的产品实现为 `7c64eb5dcad6e5f20fb7eb41819be2521f65484d`。Task 4.1 的 B PASS 快照为 `0e7b26b381ed5f71781e75d317275afa51d791e9:TASK.md`；Task 4.2 对实现 `86946cc4ef5c0648b71aafc00aa666f2a2bb20c5` 的最终 B PASS 与独立重启补证保留在 `a06a80fac90a86085f25116568aa24b54847c562:TASK.md`。当前 [Task 4.3](TASK.md) 为 PLANNED，Base 为该 B PASS 提交，按 [固定交付方案](docs/slice-4-delivery-plan.md) 继续。换机不改变合同／审查历史；原始本机证据不随 GitHub clone 传输，复用规则见 [迁移流程](docs/development-workflow.md#开发服务器迁移)。

## 产品目标

- 未变化且有主媒体流时复用；URL 不变且 SHA-1 相同忽略 Size，SHA-1 不可比时比较有效 Size；Modified 不参与。
- URL 改变始终探测，成功后使用并保存新地址；allowMediaProbe=false 不被提高权限。
- 首次默认信任已有主流；变化指纹只在本次原生探测成功、结果已保存且 STRM 未再变后提交。失败保留旧指纹，下次重新比较。
- 「控制台 → 计划任务 → STRM 媒体信息检查」支持原生运行／停止／定时，默认无自动触发；固定所选库候选 ID 后分批读取当前对象，只处理需要探测的项目。停止只撤销未开始工作，已开始探测继续完成并按条件提交，收尾报告实际结果，结束后才允许下一轮批量实际运行。候选 ID 内存随数量增长，完整媒体对象和活动工作按批次限制。
- 播放与批量共用 ProbeCoordinator，只共享已实际开始且仍在执行的探测，排队不共享；插件主动探测并发默认 2、允许 1～8，不限制其他原生任务或插件。

当前已接受播放／指纹／共享、完整配置页和原生批量；单版本安装包与安装恢复（RO-1）已由 B 独立 PASS，完整扫描重叠（RO-3）已由 B 独立 PASS，真实 3000 项媒体库、外部联调与 Slice Final 仍未完成。兼容性及接口定位见 [compatibility.md](docs/compatibility.md) 和 [references.md](docs/references.md)。

## 本地安装包

固定组合（Jellyfin `12.2.0`／Linux x64）的可交接安装包由仓库内工具生成并验证：

```bash
python3 scripts/package_plugin.py --configuration Release --runtime linux-x64 --output-dir artifacts/releases
python3 scripts/run_isolated_package_integration.py --package artifacts/releases/Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip --baseline-revision 7c64eb5dcad6e5f20fb7eb41819be2521f65484d --scenario all
```

第一条从固定 Release 输出与锁文件生成 ZIP、清单与摘要，拒绝损坏／缺失 native／非法路径归档；第二条在专用隔离实例上仅用归档完成干净安装、升级替换、禁用／移除／重装与负向包验证。完整说明、支持范围与备份／恢复见 [安装包说明](docs/package-installation.md)。

## 仓库检查

```bash
git status --short --branch
python3 scripts/check_governance.py
python3 -m unittest discover -s tests -v
git diff --check
```

治理与 Python 回归只验证文档文件身份、已提交合同及状态约束，不代表插件构建、探测、播放或独立审查通过。

`scripts/bootstrap_repository.py` 与 `bootstrap-manifest.json` 是 V3.0 首次初始化历史，当前已初始化仓库不得重新运行，也不重生成旧清单。当前治理使用 V4.3 方案身份及维护中的文件清单；需要追溯旧初始化时读取 Git 历史。
