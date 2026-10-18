# Jellyfin STRM Probe Optimizer

按版本化 STRM 的 URL、内容 SHA-1 和字节 Size 判断是否需要 Jellyfin 原生探测。V4.3 采用播放自动检查、Jellyfin 原生批量计划任务和共享并发控制；URL 改变一律要求探测。

项目：`Jellyfin.Plugin.StrmProbeOptimizer`，C# 插件。SQLite 仅保存最小历史指纹，媒体流继续保存在 Jellyfin 原生库，不维护独立探测状态机。

当前进度、验收状态和不可变证据只维护在 [Slice 合同](SLICE.md)、[Task](TASK.md) 与 [关闭账本](docs/progress.md)。本 README 只提供项目入口和可执行命令；不要在这里复制 Task 状态或审查计数。

## 开发基准与范围

[V4.3 方案](<Jellyfin STRM Probe Optimizer V4.3 开发方案.md>) 是当前基准，仅修订 V4.2 的扫描方式；V4.2 原文保留在 Git 历史。V3.0 已按用户改动从工作区移除，原文及旧合同可在 Git 检查点 `4b1d0468c1e43e6e9034ef98e99b6cc44ea59485` 中读取；不改写历史。

**不开发 STRM 生成程序。** 插件只读现有 STRM，不调用 OpenList 元数据 API、不下载媒体计算哈希、不改写 JellyfinProxy。首版不开发独立调度器、独立任务按钮、仅更新路径服务或扫描后自动触发，见 [范围说明](docs/scope.md)。

## 文档入口

1. 规则与职责：[AGENTS.md](AGENTS.md)、[开发流程](docs/development-workflow.md)、[V4.3 方案](<Jellyfin STRM Probe Optimizer V4.3 开发方案.md>)。
2. 当前工作：[SLICE.md](SLICE.md)、[TASK.md](TASK.md)、[路线图](docs/roadmap.md)、[进度账本](docs/progress.md)。
3. 产品说明：[需求](docs/requirements.md)、[用户旅程](docs/product-experience.md)、[架构](docs/architecture.md)、[范围](docs/scope.md)。
4. 操作与验证：[开发环境](docs/development-environment.md)、[配置](docs/core-configuration.md)、[安装包](docs/package-installation.md)、[测试矩阵](docs/test-matrix.md)、[兼容性](docs/compatibility.md)。

新主机按 [开发环境](docs/development-environment.md) 准备 SDK、镜像锁和隔离实例；换机不改变合同或历史证据。原始本机证据不随 Git clone 传输，复用规则见 [迁移流程](docs/development-workflow.md#开发服务器迁移)。

## 产品目标

- 未变化且有主媒体流时复用；URL 不变且 SHA-1 相同忽略 Size，SHA-1 不可比时比较有效 Size；Modified 不参与。
- URL 改变始终探测，成功后使用并保存新地址；allowMediaProbe=false 不被提高权限。
- 首次默认信任已有主流；变化指纹只在本次原生探测成功、结果已保存且 STRM 未再变后提交。失败保留旧指纹，下次重新比较。
- 「控制台 → 计划任务 → STRM 媒体信息检查」支持原生运行／停止／定时，默认无自动触发；固定所选库候选 ID 后分批读取当前对象，只处理需要探测的项目。停止只撤销未开始工作，已开始探测继续完成并按条件提交，收尾报告实际结果，结束后才允许下一轮批量实际运行。候选 ID 内存随数量增长，完整媒体对象和活动工作按批次限制。
- 播放与批量共用 ProbeCoordinator，只共享已实际开始且仍在执行的探测，排队不共享；插件主动探测并发默认 2、允许 1～8，不限制其他原生任务或插件。

稳定业务规则见 [需求](docs/requirements.md)；当前是否已验收、延期或阻塞以 [进度账本](docs/progress.md) 和当前合同为准。接口来源与版本定位见 [参考来源](docs/references.md)。

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

治理与 Python 回归只验证文档身份、已提交合同及状态约束，不代表插件构建、探测、播放或独立审查通过。Developer 只运行改动文件直接影响的测试；完整全量回归由 B 承担，规则见 [开发流程](docs/development-workflow.md#测试等级)。

`scripts/bootstrap_repository.py` 与 `bootstrap-manifest.json` 是 V3.0 首次初始化历史，当前已初始化仓库不得重新运行，也不重生成旧清单。当前治理使用 V4.3 方案身份及维护中的文件清单；需要追溯旧初始化时读取 Git 历史。
