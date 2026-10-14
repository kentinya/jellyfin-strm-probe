# Slice 关闭账本

只记录已经完成 A 最终审查的 Slice，不复制逐 Task 日志。

| Slice | Base SHA | Implementation Head | A Final Review |
|---|---|---|---|
| 1 — Jellyfin 核心接入与指纹提交验证 | `8a6a955357a6fe7a6aea9dafead0ec33ffd203f3` | `2b1e1b5bcf77b06997fabed5a31147838db16b47` | PASS / CLOSED；2026-10-13；[关闭快照与证据](#slice-1-closed) |
| 2 — 播放检查与历史指纹完整闭环 | `924816a84c74f5d79c107478f2d40e621cb8be8d` | `59fd3f7e4b6623449a691574fb69b817db72c2ae` | PASS / CLOSED；2026-10-14；[关闭范围与证据](#slice-2-closed) |

<a id="slice-1-closed"></a>
## Slice 1 关闭快照与证据

Slice 1 交付固定 Jellyfin 12.2.0 的最小核心原型：未变化零探测、地址变化原生探测、本次结果与事务保存关联、失败／竞态保留基线，以及当次与重启正确地址／主流。完整产品仍未交付。

- A 关闭检查点：`924816a84c74f5d79c107478f2d40e621cb8be8d`。该提交的 `SLICE.md` 保留完整合同、Closure Packet、A Final Review 和 Closure Reconciliation；该提交的 `TASK.md` 保留已接受 Task／B 指针。通过 `git show 924816a84c74f5d79c107478f2d40e621cb8be8d:SLICE.md` 读取，不复制历史合同到新的当前 Slice。
- Task 1.1 Base：`b69a930495c762fe546f8970891a2c955766b28c`；合同检查点：`4c749d7cce0f48b5c8146755db43837960e79f4f`；B 独立审查 PASS 检查点：`15ce799b1ca0330378f498a4cd83ec8064cae783`。完整计划／Developer 报告／历史审查位于 `46766d1eee5c7478a1aee1372a460b27ba4577bb:TASK.md`，历史 FAIL／NOT RUN 不改写。
- 单独 Slice Final：固定 SDK 构建／质量门槛、32 项 C# 与 30 项工具回归、真实隔离加载／播放／失败／竞态／重启均 PASS；A 核验原始证据和输入身份后明确复用，没有把当前文档提交当成实现或重新执行产品验收。
- 原始本机索引：`.git/validation-evidence/2b1e1b5bcf77b06997fabed5a31147838db16b47/` 下的 `slice-final-20261013/INDEX.md`、`b-review-20261013/INDEX.md`、`a-final-review-20261013/INDEX.md`。仅本工作区可读；版本、原生事务／失败对照及限制另见 [兼容性](compatibility.md) 与 [环境交接](development-environment.md)。
- 接受范围仍是进程内 `primary` 原型；SQLite、多源／通用共享、批量、完整矩阵、外部代理和发布未在 Slice 1 通过。内部数据库故障实机注入、镜像整体构建溯源和通用性能证明未宣称完成。

<a id="slice-2-closed"></a>
## Slice 2 关闭范围与证据

Slice 2 交付完整版本 1 解析／决策、首次信任、五字段 SQLite 条件提交及重启恢复、稳定项目／媒体源、多源播放按需原生探测、实际开始后的共享／正常收尾、全局并发及核心配置。URL 变化后的原生地址／主流、失败／竞态恢复与调用者权限均有分层证据；完整产品仍未交付。

- A 关闭检查点：`6da90ab6bd8995d8204ae0b7faf786c823699fe6`。A 对完整 `924816a84c74f5d79c107478f2d40e621cb8be8d..59fd3f7e4b6623449a691574fb69b817db72c2ae` 裁定 PASS，P0/P1 Blockers 为 NONE FOUND。该关闭提交的 `SLICE.md` 保留完整合同、停止／共享边界修订、Closure Packet、A Final Review 与 Closure Reconciliation，`TASK.md` 保留 B PASS 指针；通过 `git show 6da90ab6bd8995d8204ae0b7faf786c823699fe6:SLICE.md` 读取。关闭提交只协调文档，不移动 Base 或扩展实现范围。
- Task 2.1 Base `7e0240cd1cada74f142b7b0afd612943ca991a91`，实现 `198f4ff2accd5bc9fcd87518a9684b9d068de103`；完整计划／报告／B PASS 在 `13cb8bdac319fcf0b3e7500661bae1c7455077b0:TASK.md`。Task 2.2 Base 为该 B 检查点，实现为 Slice Implementation Head；完整记录在 `76cd9e997548c4ffef04a8dd8f9b0d4ef4376347:TASK.md`。历史修正／FAIL／NOT RUN 保留，不复制流水账。
- 单独 Slice Final 的 locked restore／Release build／format、112 C#／30 Python、默认隔离实机与未安装／播放检查关闭补充对照全部通过。A 核验 40 个输入／27 个产物／八个合同章节后明确复用原始 Final；另独立重跑 C# 112/112，不把旧 Task 运行或关闭文档当作新实机验收。
- 原始本机索引：`.git/validation-evidence/59fd3f7e4b6623449a691574fb69b817db72c2ae/` 下的 `b-rereview-20261014-08/INDEX.md`、`slice-final-20261014-09/INDEX.md` 与 `a-final-review-20261014/INDEX.md`；Task 2.1 索引位于对应实现 SHA 下的 `b-rereview-20261014-03/INDEX.md`。仅本工作区可读；原始命令、摘要、计数、日志及恢复清理均可核验。
- 已接受范围不含完整配置页、原生批量／实际停止收尾、大规模／扫描、外部代理、发布或跨版本兼容。逐分支 T09～T11、audio-only 实机、内部数据库故障实机注入、完整镜像构建溯源和通用性能证明仍 NOT RUN；具体分层状态见 [测试矩阵](test-matrix.md)。

## 当前开发指针

- 开发基准：V4.2；Slice 1／2 PASS / CLOSED，V3.0 与历史失败保留在 Git／原始证据。
- 当前 [Slice 3](../SLICE.md)：ACTIVE，真实 Base 为 Slice 2 关闭提交 `6da90ab6bd8995d8204ae0b7faf786c823699fe6`，Implementation Head 为 NOT SET。
- 用户目标是完整配置／所选库分页按需批量、原生运行／定时／停止收尾、播放混合共享及可对账结果；七个 Required Outcomes 与最终 T4 门槛见当前合同。新能力尚未实现／验收。
- 当前 [TASK.md](../TASK.md) 无活动实施任务；由 B 在已提交合同上判断合法性并计划首个 Task，不沿用旧 Task。Slice 4 保持 PLANNED。
- 公共 PlaybackInfo 的 None token、原生取消异常保护、只共享已开始探测及批量仅撤销未开始工作的规则不变；历史 Material Contract Change 见 Slice 2 关闭快照。
- 完整配置页／真实批量／定时／停止／统计仍 NOT RUN；本轮只有合同与事实指针，不运行产品验收、不修改运行实例。

NEXT ACTION: B PLANS FIRST TASK
