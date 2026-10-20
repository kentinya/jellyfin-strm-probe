# NO ACTIVE IMPLEMENTATION TASK

## 2026-10-20 A 合同变更交接

用户明确授权 A 不验证 JellyfinProxy、调整相关文档。本轮是 Material Contract Change，不是 Task 4.4 实施、B 审查 PASS 或 Slice 最终关闭。

- 当前 [Slice 4](SLICE.md) 仍 ACTIVE，原 Slice Base 不变；RO-1～RO-3、AC-1～AC-6、AC-8 的非代理门槛与全部安全／正确性不变量保留。
- 原 Task 4.4 为 PLANNED，未实施、未验收。ID 4.4、Task Base `57c5072db0cebf4bcf5fa64c3cde635e9a23dcb3`、原 Contract Checkpoint `539c01ca8ba4f0ce8c9eb59b32b88bbb337e7ce3` 和完整计划保留于 `4cc02048fb50c3c0b50a1b1b116246b202d86aaf:TASK.md`，用 `git show 4cc02048fb50c3c0b50a1b1b116246b202d86aaf:TASK.md` 读取，不建永久副本、不改写旧状态、不记 PASS。
- 代理专属版本／依赖／镜像构建、缓存场景、302／GET／Range、代理客户端内容和联调入口不再实施或验证；历史 NOT RUN（按用户授权不执行），不宣称兼容。缓存陈旧只是旧计划的待验证风险，不是已证实缺陷。
- 原生 PlaybackInfo／MediaSourceId→URL、正确主流、换地址后首次／重启、失败修复、多版本选源、MP4／MKV 原生 Web 实际播放仍由 RO-1／RO-3 和最终回归承担；不因撤出代理漏掉义务。
- Task 4.1／4.2／4.3 已有 B PASS，最终 4.3 快照为 `57c5072db0cebf4bcf5fa64c3cde635e9a23dcb3:TASK.md`，接受实现 `8573dfbffebb785261668f9cd5c895be937e000e`；不移动 Task Base、不撤销历史失败、不夸大未经适配命令的结果。
- 单独 Slice Final、最终同 ZIP 的安装恢复／扫描／全部 1004 项大库与成本／原生播放等完整门槛、支持说明协调、Closure Packet 和 A 最终审查均未完成。Final 仍须补齐变化批量源及多版本 A／B 的完整重启前后只读状态和显式选源，不只信旧扫描标签。

## 后续责任与停止边界

A 先提交本轮合同。B 在新合同提交上运行治理检查并明确重判旧 4.4 计划：停止代理实施，核对 RO／Surfaces／AC 和剩余非代理事项；无实施缺口时直接进入单独 Slice Final，不另造只跑测试／交接的 Task。若有真实必要实施缺口，B 先明确合同内计划；不能凭旧代理计划实施。本轮 A 不代 B 作独立审查、不运行 Final、不提前置 READY FOR A REVIEW／PASS。

本轮只改文档；不改插件、脚本／测试、依赖、运行配置或 V4.3 方案原文，不部署、不操作生产、不清理现存 1004 项库／基线／副本，不推送或发布。

## 本轮 A 文档修订检查

- 开工 main 工作区干净；原提交 4cc02048fb50c3c0b50a1b1b116246b202d86aaf，治理检查 PASS；没有待保留的工作区修改。
- 仅修改 16 个 Markdown 文件；RO-1～RO-3／AC-1～AC-6 逐行保持，全部安全／正确性不变量保留；原 V4.3 方案字节不变，Slice Base 和所有历史 Task Base／B 决定不变。
- python3 -m unittest discover -s tests -p 'test_governance.py' -v：26/26 PASS；改动文档的 162 个本地链接／锚点与代码围栏检查 PASS；git diff --check PASS。检查脚本首次遗漏 HTML 显式锚点，修正检查方式后通过；不是产品测试失败或通过。
- C# build／test／format、全量 Python、安装包／扫描／大库／播放实机及 Slice Final：本轮 NOT RUN（文档授权，不实施或替代 B 独立验收）。代理验收按用户授权不执行，历史 NOT RUN；未操作容器／生产／准备库，未推送或发布。
- 新合同必须形成普通本地提交后再执行已提交治理检查；治理通过仅代表合同／状态合法，不是 Task／产品／Slice PASS。

## 2026-10-20 B 合同重核与旧 4.4 裁决

- Reviewed Contract Checkpoint：`65286326aaf933510a0645296ec36f8721aa1bc5`；开工 `main` 干净，治理检查 PASS。核对范围是新合同、原 4.4 计划、4.1～4.3 接受记录、实际代码／工具和可读取的原始证据，不是重新签发三个历史 Task PASS。
- **决定：停止旧 4.4 代理计划；未实施、历史 NOT RUN，按用户授权不执行，不记 PASS。未发现需要新增实施 Task 的非代理缺口，直接准备独立 Slice Final。** 当前没有活动实施任务，不以测试／交接或非阻塞 P2 另造 4.4。
- Slice 仍 ACTIVE；本轮没有完成 Slice Final、Closure Packet 或 A 最终审查，不提交 READY FOR A REVIEW。所有 Base、历史失败和已有 B 决定保持。

### 保留结果与 Surface 归属

| 保留义务 | 已接受的实施／Task 证据 | 最终仍需独立验证 |
|---|---|---|
| RO-1、AC-1／AC-2：ZIP、依赖／许可／身份、干净安装、已有安装升级、配置与指纹保留、禁用／移除／重装恢复 | 4.1 B PASS：`0e7b26b381ed5f71781e75d317275afa51d791e9:TASK.md`；现有打包与包验收入口 | 最后同一 ZIP 的 package all；MP4／MKV 原生 Web 实际播放、同哈希换地址首次及重启、恢复均保留 |
| RO-2、AC-3／AC-4：全部 1004 项、首次信任／未变／增量、范围／结算、ID 与对象成本、停止／收尾／恢复 | 4.3 B PASS：`57c5072db0cebf4bcf5fa64c3cde635e9a23dcb3:TASK.md`；接受实现 `8573dfbffebb785261668f9cd5c895be937e000e` | reuse all、下限 1000 且保留实际全部 1004 项；独立成本／源／原始探测／退出和收尾核对 |
| RO-3、AC-5／AC-6：完整扫描重叠、有限变化、原生手动刷新、定时／共享／并发／停止／故障、源身份与地址／主流 | 4.2 B PASS：`a06a80fac90a86085f25116568aa24b54847c562:TASK.md`；scan all 与既有开发部署回归入口 | scan all＋完整 plugin／batch／configuration 回归；变化批量源和多版本 A／B 的三阶段重启补证 |
| 所有保留 Surface、AC-8：solution／固定 SDK／锁、配置页面／原生任务、原生 PlaybackInfo／显式选源、证据／恢复／支持文档 | 上述三项接受实现共同覆盖；没有因撤出代理遗失原生义务 | 当前合同完整回归、包／安装负载身份、原始证据与恢复核验、支持说明事实协调；之后才形成 Closure Packet |

原生 PlaybackInfo 成功状态码不能代替正确 MediaSourceId→URL、必要主流或真实 Web 播放；历史 Task PASS 也不能拼成新 Final。

### 本轮实际核验与限制

- `8573dfbffebb785261668f9cd5c895be937e000e..65286326aaf933510a0645296ec36f8721aa1bc5` 仅 16 个 Markdown 文件变化；没有可执行源码、测试／工具、依赖或运行配置变化。RO-1～RO-3／AC-1～AC-6 逐行未变，V4.3 原文逐字节未变。
- 独立重算现存 Task 4.3 审查索引的 **65 个源码／工具／测试输入**，全部匹配；重算 plugin 22、batch 21、configuration 133、scan 54，共 **230 个历史原始文件**摘要，全部匹配。核对了原始整体结果、执行退出记录和恢复状态；扫描原始审计记录真实扫描与批量／播放重叠及 136 源对账。这里只确认历史证据可核验，不称为新执行或完整 Slice Final。
- 只读运行 `python3 scripts/package_plugin.py --verify artifacts/releases/b-review-b2f19c2/Jellyfin.Plugin.StrmProbeOptimizer_linux-x64.zip`：PASS，对照 sidecar 校验归档与负载。ZIP SHA-256 为 `4066980f5d67768ad98d660cbd2f0ba250a9f70c149bad65a4a5f2a8e14a117d`；其原构建源码为 `b2f19c24f05d806ab75f152f36a302582e60ad67`，不能改称当前 HEAD 构建。当前实际构建输入摘要与包记录一致：`362df04af4af539add03017bf129747581345e813a27ef6f0645f3da0763bbda`。此项不是重新安装验收。
- 历史门禁首次文档治理失败仍保留于 `final-checks.json`，后续成功是 `final-checks-corrected.json`，没有将第一次失败改写。plugin／batch 的成功运行使用已披露的私有异步夹具准备适配；不是未经适配原命令的成功证明，不能推导冷启动 FullRefresh 普遍低于 2.5 秒。
- 已检查扫描工具 `convergence`：重启前只检查部分指纹，重启后先发 PlaybackInfo，未单独证明首次播放前全部持久化状态。沿用 4.2 的非阻塞工具 P2，Final 必须另补必要结果；不因此新增产品修复／工具扩建 Task。旧主机 4.2 补证原目录本机不可读，不假称重新核验过其原始文件，不撤销既有已提交决定。
- 本轮私有审计：`.git/validation-evidence/65286326aaf933510a0645296ec36f8721aa1bc5/b-contract-recheck-20261020T134026Z/`，仅本地可读。未启动／停止／改动容器、准备库或生产，未推送。

### 独立 Slice Final 执行准备

真实实现候选保持 `8573dfbffebb785261668f9cd5c895be937e000e`；新合同／本轮报告是文档后继，最终索引另记实际被测 checkout SHA 和输入摘要。`Implementation Head` 在最终交接时填写真实实现，不能填写本轮文档提交冒充实现。

1. 在当前合同的最后候选上新建独立 Final 索引，记录实际主机、固定 SDK／锁／镜像、资源预算、唯一归属、命令／cwd／退出／耗时、源码与夹具摘要。复用现存全部 1004 项准备数据，先核验停止状态／归属／文件／原生源／地址／主流及一致离线基线；只在新归属副本显式备份并重置首次信任用指纹，不改原库、不重建、不全库重新准备主流。不得将本轮历史摘要核验当成新运行的前置状态检查。
2. 运行 [SLICE 的最终验证](SLICE.md#最终验证) 全部 locked restore／Release build／C# test／format、全量 Python、plugin、batch suite、configuration all、治理／diff／Markdown 检查。开发部署回归与归档安装分开留证。沿用异步准备前提时显式保存适配源码／摘要：多版本及停止前等待准备扫描结束、饱和池计时前完成原生冷路径预热、mixed 删除前等待已排队刷新结束；不放宽原断言／时间阈值、不隐藏失败或反复盲跑。
3. package／scan／large 三类只消费同一最终 ZIP。可复用上述已核验 ZIP，并如实记录原构建 SHA 与当前相同输入；若在新的 checkout 打包，使用其真实 HEAD，不伪传旧 SourceRevisionId，新的 ZIP 必须一致用于三类完整 Final。

以下为现有入口的执行命令模板；`FINAL_ZIP`、`FINAL_EVIDENCE`、`PREPARED_WORKSPACE` 在运行前填入已核验的绝对路径并记录，模板不是已执行结果：

```bash
python3 scripts/run_isolated_package_integration.py --package "$FINAL_ZIP" --baseline-revision 7c64eb5dcad6e5f20fb7eb41819be2521f65484d --scenario all --evidence-dir "$FINAL_EVIDENCE/package-all"
python3 scripts/run_isolated_scan_integration.py --package "$FINAL_ZIP" --scenario all --evidence-dir "$FINAL_EVIDENCE/scan-all"
python3 scripts/run_isolated_large_library_integration.py --package "$FINAL_ZIP" --reuse-workspace "$PREPARED_WORKSPACE" --count 1000 --scenario all --reset-copied-fingerprints --evidence-dir "$FINAL_EVIDENCE/large-all"
```

4. scan all 的 Final 运行须由 B 在现有重启点加独立只读观察（可用本轮私有包装，不扩建正式工具）：对变化批量源及合并多版本 A／B，分别保存**重启前、重启后首次 PlaybackInfo 前、逐源显式选源后**的完整五字段指纹、当前 Manifest／原生地址和必要主流签名。跨重启使用重启前独立预期核对全部三源，确认零额外探测；不得用首播修复后的结果掩盖重启时缺失。正式工具标签不能单独关闭此项。
5. 独立核对原始源／候选／实际探测／保存／进度／内存／成本、整体退出及服务正常收尾；不只看局部 `full_task_acceptance` 字段。保留失败与适配，恢复配置／触发器／临时夹具；1004 项准备库及基线继续保留，不因 Final 或 Slice 结束自动清理。全部当前门槛通过并完成事实协调后，B 提交一份 Closure Packet／READY FOR A REVIEW，由 A 审完整 Base..Implementation Head 并决定关闭。

本轮 C# build／test／format、全部真实安装／扫描／大库／播放回归及 Slice Final **NOT RUN**。当前完成的是 B 合同／剩余实施缺口核对与 Final 准备，不是最终产品放行。

本轮文档检查：`python3 -m unittest discover -s tests -v` **262/262 PASS**（含 26 项治理回归）；4 个修改 Markdown 的 26 个本地文件／锚点链接和代码围栏检查 PASS；`git diff --check` PASS。开工已提交合同治理 PASS；本轮提交后另检查已提交治理，结果存入同一私有索引。上述检查不替代 Final 的 C#／实机门槛。

NEXT ACTION: B RUNS THE INDEPENDENT SLICE 4 FINAL WITH THE RETAINED RESTART PROOF; NO NEW IMPLEMENTATION TASK
