# Slice 关闭账本

只记录已经完成 A 最终审查的 Slice，不复制逐 Task 日志。

| Slice | Base SHA | Implementation Head | A Final Review |
|---|---|---|---|
| 1 — Jellyfin 核心接入与指纹提交验证 | `8a6a955357a6fe7a6aea9dafead0ec33ffd203f3` | `2b1e1b5bcf77b06997fabed5a31147838db16b47` | PASS / CLOSED；2026-10-13；[关闭快照与证据](#slice-1-closed) |
| 2 — 播放检查与历史指纹完整闭环 | `924816a84c74f5d79c107478f2d40e621cb8be8d` | `59fd3f7e4b6623449a691574fb69b817db72c2ae` | PASS / CLOSED；2026-10-14；[关闭范围与证据](#slice-2-closed) |
| 3 — Jellyfin 原生批量检查任务 | `6da90ab6bd8995d8204ae0b7faf786c823699fe6` | `7c64eb5dcad6e5f20fb7eb41819be2521f65484d` | PASS / CLOSED；2026-10-16；[关闭范围与证据](#slice-3-closed) |
| 4 — 大规模集成与单版本交付 | `03169b07d110964562f7da31d2c3d7add82e5ff5` | `8573dfbffebb785261668f9cd5c895be937e000e` | PASS / CLOSED；2026-10-20；[关闭范围与证据](#slice-4-closed) |

<a id="slice-1-closed"></a>
## Slice 1 关闭快照与证据

Slice 1 交付固定 Jellyfin 12.2.0 的最小核心原型：未变化零探测、地址变化原生探测、本次结果与事务保存关联、失败／竞态保留基线，以及当次与重启正确地址／主流。以下保留该次关闭时的接受范围，后续交付见各 Slice 关闭记录。

- A 关闭检查点：`924816a84c74f5d79c107478f2d40e621cb8be8d`。该提交的 `SLICE.md` 保留完整合同、Closure Packet、A Final Review 和 Closure Reconciliation；该提交的 `TASK.md` 保留已接受 Task／B 指针。通过 `git show 924816a84c74f5d79c107478f2d40e621cb8be8d:SLICE.md` 读取，不复制历史合同到新的当前 Slice。
- Task 1.1 Base：`b69a930495c762fe546f8970891a2c955766b28c`；合同检查点：`4c749d7cce0f48b5c8146755db43837960e79f4f`；B 独立审查 PASS 检查点：`15ce799b1ca0330378f498a4cd83ec8064cae783`。完整计划／Developer 报告／历史审查位于 `46766d1eee5c7478a1aee1372a460b27ba4577bb:TASK.md`，历史 FAIL／NOT RUN 不改写。
- 单独 Slice Final：固定 SDK 构建／质量门槛、32 项 C# 与 30 项工具回归、真实隔离加载／播放／失败／竞态／重启均 PASS；A 核验原始证据和输入身份后明确复用，没有把当前文档提交当成实现或重新执行产品验收。
- 原始本机索引：`.git/validation-evidence/2b1e1b5bcf77b06997fabed5a31147838db16b47/` 下的 `slice-final-20261013/INDEX.md`、`b-review-20261013/INDEX.md`、`a-final-review-20261013/INDEX.md`。仅本工作区可读；版本、原生事务／失败对照及限制另见 [兼容性](compatibility.md) 与 [环境交接](development-environment.md)。
- 该 Slice 接受范围为进程内 `primary` 原型；SQLite、多源／通用共享、批量、完整矩阵、外部代理和发布未在 Slice 1 通过。内部数据库故障实机注入、镜像整体构建溯源和通用性能证明未宣称完成。

<a id="slice-2-closed"></a>
## Slice 2 关闭范围与证据

Slice 2 交付完整版本 1 解析／决策、首次信任、五字段 SQLite 条件提交及重启恢复、稳定项目／媒体源、多源播放按需原生探测、实际开始后的共享／正常收尾、全局并发及核心配置。URL 变化后的原生地址／主流、失败／竞态恢复与调用者权限均有分层证据；以下只记录该次关闭范围，不将后续交付倒写为本 Slice 结果。

- A 关闭检查点：`6da90ab6bd8995d8204ae0b7faf786c823699fe6`。A 对完整 `924816a84c74f5d79c107478f2d40e621cb8be8d..59fd3f7e4b6623449a691574fb69b817db72c2ae` 裁定 PASS，P0/P1 Blockers 为 NONE FOUND。该关闭提交的 `SLICE.md` 保留完整合同、停止／共享边界修订、Closure Packet、A Final Review 与 Closure Reconciliation，`TASK.md` 保留 B PASS 指针；通过 `git show 6da90ab6bd8995d8204ae0b7faf786c823699fe6:SLICE.md` 读取。关闭提交只协调文档，不移动 Base 或扩展实现范围。
- Task 2.1 Base `7e0240cd1cada74f142b7b0afd612943ca991a91`，实现 `198f4ff2accd5bc9fcd87518a9684b9d068de103`；完整计划／报告／B PASS 在 `13cb8bdac319fcf0b3e7500661bae1c7455077b0:TASK.md`。Task 2.2 Base 为该 B 检查点，实现为 Slice Implementation Head；完整记录在 `76cd9e997548c4ffef04a8dd8f9b0d4ef4376347:TASK.md`。历史修正／FAIL／NOT RUN 保留，不复制流水账。
- 单独 Slice Final 的 locked restore／Release build／format、112 C#／30 Python、默认隔离实机与未安装／播放检查关闭补充对照全部通过。A 核验 40 个输入／27 个产物／八个合同章节后明确复用原始 Final；另独立重跑 C# 112/112，不把旧 Task 运行或关闭文档当作新实机验收。
- 原始本机索引：`.git/validation-evidence/59fd3f7e4b6623449a691574fb69b817db72c2ae/` 下的 `b-rereview-20261014-08/INDEX.md`、`slice-final-20261014-09/INDEX.md` 与 `a-final-review-20261014/INDEX.md`；Task 2.1 索引位于对应实现 SHA 下的 `b-rereview-20261014-03/INDEX.md`。仅本工作区可读；原始命令、摘要、计数、日志及恢复清理均可核验。
- 已接受范围不含完整配置页、原生批量／实际停止收尾、大规模／扫描、外部代理、发布或跨版本兼容。逐分支 T09～T11、audio-only 实机、内部数据库故障实机注入、完整镜像构建溯源和通用性能证明仍 NOT RUN；具体分层状态见 [测试矩阵](test-matrix.md)。

<a id="slice-3-closed"></a>
## Slice 3 关闭范围与证据

Slice 3 交付完整配置页／所选媒体库、Jellyfin 原生「STRM 媒体信息检查」的运行／停止／定时、候选 ID 固定后分批读取及按需检查、播放混合共享、停止收尾和准确故障反馈。首次信任不引起全库重探测；已开始探测不因批量停止取消，满足原成功条件仍提交，旧轮收尾后才允许下一轮实际运行。

- A 审查完整 `6da90ab6bd8995d8204ae0b7faf786c823699fe6..7c64eb5dcad6e5f20fb7eb41819be2521f65484d` 后裁定 PASS / CLOSED，P0/P1 Blockers 为 NONE FOUND，AF-1 CLOSED。审查 checkout `aa78c06216ec30fbefd288ac4c73e9a7d44afa95`；A 关闭检查点 `03169b07d110964562f7da31d2c3d7add82e5ff5` 的 `SLICE.md` 保留完整合同、候选 ID 方案修订、Closure Packet、A Final Review 和 Closure Reconciliation，`TASK.md` 保留完整 B PASS 指针。可用 `git show 03169b07d110964562f7da31d2c3d7add82e5ff5:SLICE.md` 读取。只协调文档，不移动 Base、不扩展接受实现、不激活下一 Slice。
- Task 3.1 Base `b86d9c17d7f915108072f54ee098f0f5543fe093`、接受实现为上表 Slice 3 的 Implementation Head，完整计划／报告／B PASS 在 `aa78c06216ec30fbefd288ac4c73e9a7d44afa95:TASK.md` 及可达历史。Task 3.2 Base `2f74aa83f15707df56c4b15409ba1538a488f83a`、实现 `5580492a5cacbdc0772dd2f14f9b527ab3851746`，历史 B PASS 在 `678bcf5c3a6ba5c6743402ec27367dd76d0f101d:TASK.md`。旧 A 拒绝及历次修正／FAIL 保留，不重写为 PASS。
- 新单独 Slice Final：locked restore／Release build／format、202 C#／63 Python、默认真实播放、七场景 batch 与配置页 19 个浏览器场景全部 PASS，无 Final 门槛失败／重试。配置／全部触发器／夹具恢复、临时条目清理。A 核验 82 项输入、232 项构建产物及 405 个证据摘要后明确复用真实 Final；另独立复跑全部 C#／Python 与 16 项准入／末项故障控制，全部 PASS，未声称 A 再次实机运行。
- 本机索引：`.git/validation-evidence/7c64eb5dcad6e5f20fb7eb41819be2521f65484d/` 下的 `slice-final-20261016/INDEX.md`、`b-review-20261016/INDEX.md` 与 `a-final-review-20261016/INDEX.md`。仅本工作区可读；原始命令、身份、日志、计数、交互／截图、恢复和复用范围均可核验。
- 历史十万模拟候选验证有界对象／消费者及 O(N) ID 成本，代表实机验证多库多批／多版本；不构成历史真实十万库或恒定总内存证明。日志跨日关联与指数措辞保留 P2。真实大库、完整扫描压力与本地 ZIP 未在本 Slice 验证，后续结果见 [Slice 4](#slice-4-closed)；外部代理／OpenList、广泛格式／客户端、逐分支／audio-only 实机、物理数据库保存故障注入、完整镜像构建溯源与通用性能证明保持各自未验证边界。

<a id="slice-4-closed"></a>
## Slice 4 关闭范围与证据

Slice 4 交付固定 Jellyfin 12.2.0／Linux x64 的本地 ZIP、完整安装／恢复说明，以及真实大库增量、完整扫描与播放／批量重叠的分层验证。A 对完整 Base..Implementation Head 裁定 PASS，未发现 P0／P1；没有扩大跨版本、格式、客户端或通用性能支持。

- A 关闭检查点 `020b05a6cb2026fbc5e6bcdf5e868345470594fb`；审查 checkout `9b36a42307b5c1576dbb49c99b64e6d364c470cc`。该提交的 SLICE.md 保留完整合同、B Closure Packet、A Final Review 与关闭协调，TASK.md 保留当时交接和 B 决定。用 `git show 020b05a6cb2026fbc5e6bcdf5e868345470594fb:SLICE.md` 及同 SHA 的 TASK.md 读取；后续根合同切换不改写该历史。关闭只改 Markdown，不移动 Base／Implementation Head、不新增实施、不推送或激活下一 Slice。
- Task 4.1～4.3 的固定 Base..Head、报告和 B PASS 快照统一保留于上述 SLICE.md 的 Closure Packet／“B 决定、候选与审查范围”章节。旧 4.4 未实施，按用户授权停止、不记 PASS；ID／Task Base／原计划见 `4cc02048fb50c3c0b50a1b1b116246b202d86aaf:TASK.md`，撤出代理后的 B 重核见 `51319254fc4426349f7023cc0efa9d61ecbe2a26:TASK.md`。原 RO-4／AC-7 保持历史 NOT RUN，JellyfinProxy 不验证且无兼容承诺。
- B 本次独立 Final 核验并采用匹配的完整 C#／Python、plugin／batch／configuration、同 ZIP 安装／扫描／大库原始门禁，另新运行三源完整重启证明和当前文档检查；未声称重新执行所有昂贵门禁。A 独立核验输入、包、原始文件及用户结果后明确接受复用，未再次运行产品验收。原始失败、准备适配和证据缺失限制均保留。
- 原始本机索引：`.git/validation-evidence/51319254fc4426349f7023cc0efa9d61ecbe2a26/b-slice-final-20261020T140212Z/INDEX.md` 与 `.git/validation-evidence/8573dfbffebb785261668f9cd5c895be937e000e/a-final-review-20261020/INDEX.md`；只在本机，不随 Git 上传。具体 ZIP 摘要、成本、对账、补证与明确延期见合同。
- MP4／MKV 原生 Web 实际播放、安装升级及禁用／移除／重装恢复、现存全部 1004 项首次信任和未变零探测、小集合增量／停止恢复、完整原生扫描重叠、源身份／五字段／原生地址主流的重启前后证明均在本次接受范围。准备库、基线及保留副本持续供后续需要它的开发阶段复用，关闭不清理。
- P2：正式扫描工具尚未内置完整三阶段重启观察、异步准备私有适配及既有日志／措辞。其他平台／格式／客户端、OpenList 专有行为、指定逐分支及 audio-only 实机、物理数据库保存故障注入、完整镜像构建溯源和线上发布仍不在已验证声明内；不改写历史十万／3000 结果。

## 当前开发指针

开发依据为 [稳定需求](requirements.md)、维护中的架构及已提交合同，用户范围与原方案退出治理的边界见 [范围说明](scope.md)。上方是四个已完成 A 最终审查的 Slice 账本。

此前四个 Slice 的接受范围与原始证据见上方固定 Git 快照。2026-10-20 用户新增八类真实播放测试及 GitHub Actions 失败修复需求，已建立 [Slice 5 规划合同](../SLICE.md) 和 [执行设计](slice-5-playback-test-plan.md)；根 [TASK.md](../TASK.md) 无活动实施任务，下一步先由 A 激活合同、B 再规划 Task。本轮未运行新增产品验收或修复 CI，已知返回主流误判的产品修复仍待用户决定；历史接受事实不改写，现存全部 1004 项准备库持续保留。
