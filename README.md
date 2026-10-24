# Jellyfin STRM Probe Optimizer

按版本化 STRM 的 URL、内容 SHA-1 和字节 Size 判断是否需要 Jellyfin 原生探测。插件采用播放自动检查、Jellyfin 原生批量计划任务和共享并发控制；URL 改变一律要求探测。

项目：`Jellyfin.Plugin.StrmProbeOptimizer`，C# 插件。SQLite 仅保存最小历史指纹，媒体流继续保存在 Jellyfin 原生库，不维护独立探测状态机。

开发与维护状态从[当前开发指针](docs/progress.md#当前开发指针)进入；最后一个关闭合同、当前任务入口和不可变历史分别由 [SLICE.md](SLICE.md)、[TASK.md](TASK.md) 与关闭账本维护。本 README 提供项目入口和可执行命令，不复制 Task 状态或审查计数。

八类播放决策、ColorRange结果匹配及干净检出CI修复的已接受范围见[最终审查](docs/progress.md#slice-5-closed)，输入与观测设计见[播放测试计划](docs/slice-5-playback-test-plan.md)。当前授权范围的交付与下一步统一由合同和关闭账本维护。

## 开发基准与范围

当前开发依据为 [仓库约束](AGENTS.md)、[稳定需求](docs/requirements.md)、[架构](docs/architecture.md) 和已提交 Slice／Task 合同。按 2026-10-20 用户要求，V4.3 原方案退出治理，仅作可选本地参考，不再跟踪或上传 GitHub；克隆与 CI 无须该文件。历史版本与已提交审查记录保留，发布边界见 [Git 检查点](docs/development-workflow.md#6-git-检查点)。

按 2026-10-20 用户授权，当前交付不验证 JellyfinProxy，不宣称代理兼容；原生播放、安装恢复、大库与扫描验收保留，具体覆盖见 [范围说明](docs/scope.md)。范围以用户授权及当前合同为准。

**不开发 STRM 生成程序。** 插件只读现有 STRM，不调用 OpenList 元数据 API、不下载媒体计算哈希、不改写 JellyfinProxy。首版不开发独立调度器、独立任务按钮、仅更新路径服务或扫描后自动触发，见 [范围说明](docs/scope.md)。

## 文档入口

1. 规则与职责：[AGENTS.md](AGENTS.md)、[开发流程](docs/development-workflow.md)。
2. 状态与历史：[关闭合同](SLICE.md)、[当前任务入口](TASK.md)、[路线图](docs/roadmap.md)、[进度账本](docs/progress.md)。
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

固定组合（Jellyfin `12.2.0`／Linux x64）的可交接安装包由仓库内工具生成并验证；当前已接受包的身份、原生播放／大库／扫描证据和限制见[A最终审查](docs/progress.md#slice-5-closed)，具体安装步骤见[安装包说明](docs/package-installation.md)。本地安装交付不包含线上发布或插件仓库上架。

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

治理检查验证文档身份、已提交合同和状态约束；Python 回归验证现有工具与隔离保护。它们不代表 C# 插件构建、真实探测／播放或独立产品审查通过。Developer 只运行改动文件直接影响的测试；完整全量回归由 B 承担，规则见[开发流程](docs/development-workflow.md#5-测试等级)。

V3.0 一次性初始化脚本 `scripts/bootstrap_repository.py` 与 `scripts/bootstrap-manifest.json` 已从当前工作区移除，历史内容可从 `aa01231:scripts/bootstrap_repository.py` 和 `aa01231:scripts/bootstrap-manifest.json` 读取。克隆仓库后不再执行旧初始化；当前治理校验现行文档和已提交 Slice／Task，不读取本地 V4.3 原方案。`check_governance.py --bootstrap` 仅保留未初始化规划的只读检查，不负责创建 Git 或激活合同。
