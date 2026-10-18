# 开发流程

本文件是 Slice／Task 生命周期、Git 检查点、测试和审查的唯一流程定义。参考来源和固定版本见 [references.md](references.md)。长期业务规则见 [AGENTS.md](../AGENTS.md)。

## 1. 管理对象与角色

只有两个管理对象：Slice 是一个完整能力合同，Task 是合同内一个可整体审查的实施单元。V4.2 的 P0／P1／P2／P3 只用来解释方案映射；修正留在原 Task，不另造 Fix 生命周期。

| 角色 | 责任 |
|---|---|
| A：Slice 所有者／架构与最终审查 | 定义 Required Outcomes、边界、Base、验收；审查完整 Slice；协调最终事实并关闭 |
| B：Task 规划／审查 | 检查真实仓库，规划当前最大合理实施单元，审查 Task，运行完整全量回归与独立验收，判断 Slice 是否已满足 |
| Developer：实施 | 在活动 Task 内实现、只运行由改动文件直接影响的测试并报告未运行项，提交完整聚焦证据；不自行扩大范围或签发审查 PASS |

角色是责任，不是必须使用多个模型。独立审查不能由被审查实现者直接冒充；当前任务只建立流程和合同，不宣称已完成独立审查。代理委派须有用户或适用指令的明确要求。

## 2. 状态

```text
Task: PLANNED → IN PROGRESS → READY FOR B REVIEW → PASS
                              ↘ FIX REQUIRED → IN PROGRESS

Slice: PLANNED → ACTIVE → READY FOR A REVIEW → PASS / CLOSED
                         ↘ FIX REQUIRED → 同一 Slice 内修正
```

`TASK.md` 无活动实施任务时，首行为 `# NO ACTIVE IMPLEMENTATION TASK`。Task 没有 CLOSED 状态；通过后只能进入下一个合同内 Task，或提交 Slice 最终审查。

只有 A 可关闭 Slice。没有产品实现的开发基线不计为一个通过的产品 Slice。规划阶段 Base 为 `NOT SET`；激活必须使用真实可达的完整提交 SHA。

### 用户明确要求的冻结与优先级调整

只有用户明确要求时，A 才能在未关闭 Slice 时冻结开发并选择另一优先级。被冻结的 Slice 和 Roadmap 使用 `PLANNED`，合同标注 `Development Hold: FROZEN BY USER`；待用户补充内容的新 Slice 也保持 `PLANNED`。这两种状态都不允许活动实施 Task，也不表示已验收。

替换根文档或切换工作区前，在专用保留分支提交当前 Slice 所属改动及准确的 Task 报告／B 决定，记录不可变的 Slice Base、最新实现 SHA、保留分支和审查快照 SHA。无关用户改动和私有文件保持原样；不用 stash、破坏性 reset、历史改写或 Task 归档目录代替保留检查点。

根 `TASK.md` 改为 `# NO ACTIVE IMPLEMENTATION TASK`；被冻结 Task 从记录的 Git 快照恢复，保留 ID、Base、Goal、Scope 和未解决阻塞项。未明确的新请求只能记录缺失的范围，不能编造 Outcomes 或验收。已提交的 `PLANNED` 合同使用真实 Base、无活动 Task、匹配的 PLANNED Roadmap；治理检查通过仍不构成实施准入。

插入的 Slice 在已接受实现线上建立隔离分支，不能悄悄带入冻结但未接受的代码。用户补充内容后，A 先提交完整 ACTIVE 合同，B 才能计划。恢复原工作也要求 A 显式激活检查点：恢复原合同和 Task 身份／Base／边界，重新评估期间已接受的变更；不暗中 rebase、重设 Base、合入被拒代码、清空阻塞或把 FIX REQUIRED 变成 PASS。

## 3. 合同与激活顺序

`SLICE.md` 至少包含 ID、名称、Owner、Status、Base SHA、Implementation Head、用户目标、Required Outcomes／Surfaces、用户约束、业务不变量、排除范围、验收、最终验证、Closure Packet 和 A Final Review。

合法顺序：

```text
真实基线提交
→ A 的 Slice 合同激活提交（Roadmap 同步为 ACTIVE）
→ B 的 Task 计划
→ Developer 实现检查点
```

Base 固定为该 Slice 实施前的基线；后来的合同、计划和文档提交不移动 Base。`Implementation Head` 记录实际实现检查点，不能用文档状态提交冒充。

Task 计划前运行 `python3 scripts/check_governance.py`：读取 `HEAD:SLICE.md` 与已提交 Roadmap，验证工作区合同一致、活动 Task 的 Parent Slice、完整 SHA 和祖先关系。没有合同提交，不能用工作区 ACTIVE 文案替代激活。

首次初始化前可运行 `--bootstrap`；它只检查 PLANNED／NOT SET／无活动 Task 的规划状态和文件完整性，输出不算实施准入。

### 合同澄清、实质变更与 PARTIAL / RESCOPE

只有 Required Outcomes、Required Surfaces 和正确性／安全不变量的验收含义均不变，才属于事实澄清。A 保留 Base，B 重新核查 Task 合法性。改变义务、验收含义或当前 Task 边界，即使用户目标文字相同也属于实质变更：A 提交新合同，B 明确决定当前 Task 继续、调整还是重规划，Developer 才能实施。

`PARTIAL / RESCOPE` 记录合同问题、仍有效的实现事实、已失效范围／假设及替代合同。如果原 Base 仍是真实起点，保持同一 Slice 与 Base；业务边界已使其失效时，以当前已提交 HEAD 为 Base 建立新 Slice ID，保留原部分完成记录，不把原 Slice 写成 PASS。

本次 V4.2 重规划是实质合同变更：原 Slice 1 没有产品实现，核心接入目标仍成立，保留 ID／Base 并提交修订合同；根 TASK 暂设无活动任务。B 在该提交后重规划 Task 1.1，保留原 Task Base 作为审查起点，另记录新的 Contract Checkpoint 和被替代计划快照。此记录不代表产品审查 PASS，不授权本次文档工作执行插件开发。

2026-10-14 用户授权 A 简化 Slice 3 的批量读取：允许一次获取原生候选 ID 集合、分批读取完整对象、固定消费者，不要求滑动分页／排除列表／独立等待队列。原文保留，变化属于 Material Contract Change；A 先提交修订 ACTIVE 合同及协调需求／架构，根 Task 暂无活动实施任务。B 在该提交后判断同一 Task 3.1 合法调整，保留 ID、Task Base 和原计划 Git 快照，更新 Contract Checkpoint／验收／测试；不假装产品 PASS 或启动本轮插件实施。

2026-10-18 用户授权 A 将当前大库验收从历史规划中的至少 100000 个候选调整为至少 3000 个真实原生候选。历史快照、关闭账本和既往模拟结果保留原数值并明确为历史事实；当前 ACTIVE Slice、Roadmap、Task 和同步文档使用 3000。该变化属于 Material Contract Change，B 必须在新的 Contract Checkpoint 后重新核查当前 Task 的合法性；不授权插件实施或降低其他 Required Outcome。

当前文件治理独立检查 V4.3 方案及维护中的文件清单；V4.3 是用户授权的扫描方式最小修订，沿用已提交 ID 集合合同，不移动 Slice／Task Base 或改变其验收；`bootstrap-manifest.json` 与初始化脚本是 V3.0 一次性初始化历史，不再决定当前必需文件，也不重新生成旧摘要。未来再次替换方案时，必须显式同步原文身份、需求、合同和治理回归，不能通过删除原文校验规避变更记录。

## 4. Task 规划与实施

每个 Task 使用 [模板](../Task/TEMPLATE.md)，声明 Goal、Parent Slice、Task Base、Difficulty、Test Level、范围、验收、必要测试、非目标、完成报告和 B Review Result。Goal 指向 Slice 的 Required Outcome。

通常一个 Slice 划分 3～7 个完整实施单元；超过 8 个应重新检查拆分是否只是在按类、字段或测试数量计数。按完整行为拆分，不按文件数量拆分。首个高风险接入原型可以在一个 Task 内同时验证多个紧密关联接口。

实施开始记录已有改动，区分 Task 所有与用户所有。保留用户文件；不通过 restore、checkout、reset、clean 或 stash/drop 间接删改无关内容。Task 内已授权的必要实现、修复、测试和本地提交持续执行。

Developer 提交后记录完整实现 SHA、改变文件、行为、实际测试结果、决定、剩余 Required Outcomes 和限制，将 Task 交为 `READY FOR B REVIEW`。完成报告可随后一检查点记录已存在的实现 SHA，不能把同一次提交自己的 SHA 预填进其内容。

B 审查真实 Task Base..Head，而不只读完成报告。`FIX REQUIRED` 仅列当前 Task 阻塞项，修正形成新提交，不重写已审查历史。

## 5. 测试等级

| 等级 | 适用风险 | 必要验证 |
|---|---|---|
| T0 | 不改变需求、架构或范围的事实文档同步 | 相关 Markdown／链接检查，`git diff --check` |
| T1 | 仅增加现有行为的测试 | 新测试、受影响与相关测试 |
| T2 | 单一低风险模块 | 聚焦／模块测试，相关静态检查 |
| T3 | 跨模块／Jellyfin 适配／持久化的普通集成 | 聚焦、相关集成、受影响回归、质量检查 |
| T4 | 核心服务替换、刷新、状态迁移、并发、播放正确性 | 聚焦、集成、全部已有回归及相关真实运行／包验证 |

需求和架构合同变更不能假装成普通 T0。C# 项目创建后，Task 写出真实 `.sln`／项目路径、固定 SDK 和准确 `dotnet restore/build/test/format` 命令；当前不写不存在项目的“已通过”结果。

### 测试计划与执行阶段

每个 Task 的必要测试分为开发／修正反馈、最终检查点门槛、B 独立验证、证据与重跑规则四部分。每个命令关联具体行为或风险；T0～T3 要求全套回归时说明实际原因。T4 保留完整指定门槛，Slice 的明确验证要求优先。

| 阶段 | 必要执行 |
|---|---|
| 开发／修正反馈 | Developer 只运行新增／修改测试、已知失败和由改动文件直接影响的回归，并记录未运行项目；边界变化时补相关集成或原生链路。先处理已知阻塞，再运行昂贵门槛。 |
| 最终 Task 候选 | Developer 提交改动文件直接影响的聚焦结果；B 对准备审查的候选运行完整全量回归与适用的实机／质量验证。开发反馈不能替代最终验收。 |
| B Review | B 审查真实差异和原始证据，独立复现 Task 指定的关键行为，并承担完整全量回归与独立验收；缺失、不匹配或与事实矛盾的证据要求重跑。 |
| Slice Final | 在当前合同上运行完整回归与适用的实机、打包、迁移等门槛，写入 Closure Packet。 |

完整套件在正确配置下已覆盖聚焦用例时，记录覆盖关系，不机械重复同一用例。Task／Slice 单独要求的真实 Jellyfin、重启、容器或迁移验证仍须运行。最终验证后改变可执行源码会使该候选的全套证据失效；T4 修正候选仍需完整指定门槛。

Developer 的开发反馈不要求重复全量套件：只跑新增／修改测试及直接受改动文件影响的测试，并在报告中列出未运行的全量项目。B 负责完整 C#／Python 回归、Task 指定全量门槛和独立验收；B 可复用匹配且可核验的证据，但不能以 Developer 的聚焦结果替代全量门槛。已有明确阻塞时可先拒绝，其他未运行门槛如实记录；PASS 前仍须满足完整计划。A 保留独立最终审查责任。

既有 Task 测试计划持续有效，直到 B 显式修订并记录原因。修订保持 Task ID、Base、Goal、Scope、验收与 Slice 合同；Developer 不能私自删减命令。新增接入、持久化、并发或播放权限风险返回 B 重新评估等级。

### 可核验证据与复用

每个候选／运行保留一个证据索引，包含：

- 测试时完整源码 SHA、工作区改动的准确内容身份、被审查检查点 SHA。
- 精确命令、工作目录、运行时版本、依赖／锁文件身份、脱敏夹具／配置身份、选择／并行／重试设置及构建产物摘要。
- 退出码、通过／失败／跳过／不稳定／不可用数量、耗时、原始日志和适用的计数／截图；保留首次失败与每次重跑。
- 对应的门槛／验收条件、明确复用的运行和缺失项。

带工作区改动的运行必须记录实际被测内容，并证明它与提交检查点相同。B 阅读原始产物，不能凭报告中的 PASS 标签复用。角色或 CI 来源本身不决定证据有效性；缺日志、不完整或不可核验的运行须重跑对应门槛。

只有可执行代码、测试／工具、依赖、运行配置、夹具和产物输入均匹配时，才能跨角色复用。纯报告／文档后继提交须显式比较这些输入，重新运行消费变更文档的治理／发布等检查。输入改变时更新相关证据；影响不确定时重跑。Slice Final 仍运行当前合同的最终门槛，不能用旧 Task 运行代替。

索引与原始日志保留到 A 最终决定，使用 CI 产物或稳定的忽略目录，例如 `.git/validation-evidence/<source-sha>/<run-id>/`。仅放 `/tmp` 不足以交接；本地证据不能声称远程可访问。证据不混入产品配置、普通源码提交或用户参考图片。复用、缺失和已有失败的真实 Base 复现须明确披露；不能靠删测试、弱化断言、隐藏 skip／重试或改超时制造绿灯。

结果只用真实证据：`PASS`、`FAIL`、`NOT RUN`、`BLOCKED`、`SKIPPED`。跳过或不可用须给出理由。单元假对象不能作为真实 Jellyfin DI、探测成功或重启持久化的证据。

真实验收只使用明确的隔离实例、临时库和假／本地媒体服务。外部 JellyfinProxy／OpenList 依赖不可用时如实记录，不能算联调 PASS，不自动使用生产配置。

### 开发服务器迁移

用户已于 2026-10-18 授权取消旧服务器依赖。换机继续当前 Task，不要求保留原检出绝对路径、连接旧 Docker 实例、沿用旧账户／凭据、满足旧主机资源预算或回到旧主机运行测试。仓库根目录由当前检出确定；SDK／依赖／目标 Jellyfin 身份继续固定，环境按 [开发环境](development-environment.md) 在新主机重新准备。

新主机的 CPU／内存／磁盘／端口、容器身份、测试资源与超时预算重新观测并在运行前记录。旧主机的资源不足不自动继承为新环境 BLOCKED；环境参数的迁移调整无需重新激活合同或重复申请授权。失败后的调整仍须披露原因、保留原失败，不能改变候选数量、正确性、停止语义或 T4 门槛。

Git clone／push 不传输 `.git/validation-evidence/`、忽略的 artifacts、运行数据库或凭据。旧本机证据引用保留为历史来源，不要求新主机拥有相同目录才能规划或实施，也不把缺失证据升级为 PASS。已提交的审查决定保持；需复用的原始运行可单独安全迁移并核对摘要，无法读取或核验时重跑相应门槛。当前 Task 和 Slice Final 的新候选仍按上节证据要求验证，不默认重跑已关闭 Slice，也不借迁移改写历史结论。

迁移过程只提交可公开的环境身份与说明，凭据和原始私有证据不进入普通源码提交。新运行可使用稳定 CI 产物或本机忽略目录保存证据，记录真实可访问范围；旧服务器无需继续在线。

## 6. Git 检查点

一个 Task 通常形成一个完整实现检查点；修正增加新提交。审查指明完整 SHA 或 Base..Head，不要求每个审查结果额外形成文档提交。

提交前检查 status、完整 diff、文件清单、`git diff --check`、未跟踪文件、隐私配置和 Task 范围。禁止一概 `git add .` 把用户无关文件带入；本次初始化脚本采用显式清单。

普通本地检查点按已授予的仓库权限执行。本次用户已要求 Git 版本管理，初始化脚本可创建本地提交。未经明确授权不推送、不配置参考仓库为远程、不重写历史或破坏性清理。

`.git` 不可写时停止 Git 写入并报告限制，不通过另一个 Git 目录绕开它。文件工作可继续；不能填虚构 SHA、声称已有提交，或把缺失 Git 证据当成 PASS。

## 7. Slice 停止规则与最终审查

每次 Task PASS 后 B 重新检查全部 Required Outcomes。已全部满足时，不为额外测试、非阻塞润色或未来重构再造 Task；运行 Slice Final，形成一份 Closure Packet 并将 Slice 交为 `READY FOR A REVIEW`。

Closure Packet 包含：Slice、Base／Head、Required Outcomes 完成状态、实现内容、Task 索引、最终测试、业务不变量证据、非阻塞问题、明确延期、文档协调项和 `SLICE READY FOR A REVIEW` 决定。

A 审查完整 Base..Implementation Head 和真实用户结果，A Final Review 明确记录 `Reviewed Range`、`Decision`、`P0/P1 Blockers`，可返回 PASS、FIX REQUIRED、PARTIAL / RESCOPE。FIX REQUIRED 保持 Base，交回 B 计划原 Slice 内修正，不提前填写关闭协调结果。

PASS 后在同一个关闭检查点协调 CURRENT 文档、SLICE、Roadmap、Progress、README，记录 `Closure Reconciliation` 与 `PASS / CLOSED`，将 `TASK.md` 设为无活动任务，并写明 `Next Action: A SELECTS THE NEXT LARGE SLICE`。该检查点记录已经审查的 Implementation Head，不暗中扩展产品审查范围；若协调将改变范围、架构合同或安全规则，返回 PARTIAL / RESCOPE。关闭检查点完成后停止；下一 Slice 的选择与激活是另一项动作，不能把自动铺开后续实现夹入关闭工作。

关闭检查点同时审阅三份角色经验文档；每个角色至多补充 1～3 条值得复用的新经验，用“问题 → 做法 → 适用条件”写清，合并重复、替换过时条目。没有新经验不凑数；经验不是 Task PASS 门槛，不记录提交号、计数或流水账。Developer 本项目经验在产生具体实施事实前保持空白。

P0 表示可信的播放整体不可用、状态损坏、秘密泄露等严重问题；P1 表示 Required Outcome、必要恢复或正确性不变量未满足；P2 表示非阻塞质量改进。P2 不能无限延长 Slice。关闭后发现原范围 P0／P1 时，保留原 Base 和历史审查，重新激活同一 Slice 并新增修正提交。

## 8. 文档维护

状态只写一次，其他文档通过链接引用。更新 Task 或验收事实时，先更新权威文件，再做必要的短入口同步；不复制 SHA、测试计数、审查过程或当前状态段落。

| 文档 | 唯一职责 |
|---|---|
| `SLICE.md` | 当前能力合同、Required Outcomes／Surfaces、验收和最终包 |
| `TASK.md` | 当前实施任务、测试分工、完成报告和 B 决定 |
| `Task/TEMPLATE.md` | 可复用 Task 模板 |
| `docs/roadmap.md` | 大 Slice 目标、次序、依赖和状态 |
| `docs/progress.md` | 已关闭 Slice 的简短账本与当前指针 |
| `docs/requirements.md` | 稳定需求和业务不变量，不记录当前进度 |
| `docs/product-experience.md` | 用户旅程、恢复和可见行为 |
| `docs/architecture.md` | CURRENT／TARGET 架构与模块责任，不记录审查日志 |
| `docs/test-matrix.md` | 用例身份、分层证据和未运行边界 |
| `docs/development-environment.md` | 可迁移环境、固定输入和运行前提 |
| `docs/core-configuration.md` / `docs/package-installation.md` | 可执行的配置、安装和恢复步骤 |
| `docs/compatibility.md` / `docs/references.md` | 兼容性结论、源码定位和外部来源 |
| `docs/agent-experience/` | A／B／Developer 的短经验清单，不改变合同或验收 |

详细 Task、修正和审查历史留在 Git。完成 Task 后可替换根 `TASK.md`，无需永久复制所有历史 Task 文件；保留它们的可达提交。文档治理本身属于 T0：只需相关 Markdown／链接检查和 `git diff --check`，不把文档整理写成产品验收。
