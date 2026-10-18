# Task [ID] — [一个完整实施目标]

模板受当前 [Slice](../SLICE.md) 约束，执行顺序见 [开发流程](../docs/development-workflow.md)。复制到根 TASK.md 时将链接改为根目录相对路径。

规划／审查阅读 [B 经验](../docs/agent-experience/task-planner-reviewer.md)，实施阅读 [Developer 经验](../docs/agent-experience/developer-implementation-role.md)。

```text
Task ID: [Slice.Task]
Parent Slice: [数字 ID]
Status: PLANNED
Task Base: [真实完整 SHA]
Difficulty: Low | Medium | High
Test Level: T0 | T1 | T2 | T3 | T4
Planner / Reviewer: B
```

## Goal

描述一个可审查的完整行为，并指向当前 Slice 的 RO 编号。

## 实际缺口与实施范围

记录检查过的真实代码／测试与当前缺口，列出为行为闭环需要的层、文件边界和冻结范围。不要把文件、字段或单条断言当成独立产品目标。

## 验收条件

- [ ] 完成具体用户结果，包括成功、失败和恢复。
- [ ] 保持适用的原生委托、探测权限、版本确认、路径与隐私边界。
- [ ] 指定测试等级取得真实证据；未运行／不可用单独记录。
- [ ] 提交只包含本 Task，未改变无关用户文件或 Slice 合同。

实施前替换以上示例为当前 Task 的具体标准。

## 必要测试

遵循开发流程的测试阶段与证据规则，Slice 明确验证要求优先。填入本 Task 的命令和风险，不复制整套流程。不得列出不存在项目的“已通过”命令。

### 开发／修正反馈

Developer 只列新增／修改测试、已知失败和由改动文件直接影响的回归，以及必要的集成／原生链路命令；明确列出未运行的全量项目。完整全量回归由 B 在独立验证阶段承担。

### 最终检查点门槛

指定等级的准确命令与覆盖风险。Developer 记录聚焦命令；B 负责完整指定门槛。标明完整运行已包含的聚焦用例及单独必需的实机门槛。

### B 独立验证

B 要独立复现的关键行为、运行完整全量回归和需阅读的匹配证据，并明确复用范围。

### 证据与重跑规则

稳定的忽略目录／CI 产物引用、候选及输入身份、风险对应的重跑条件。记录首败、重复、缺失和不可用项。修改既有计划时记录原因并保留 ID／Base／Goal／Scope／验收。

## 非目标

列出下一个 Task／Slice、生成程序、代理改动和不需要的重构等明确排除项。

## Developer Completion Report

- Changed Files：
- Implemented：
- Tests and Results：证据索引、被测候选、精确命令／计数／耗时、首败／重跑、复用运行和缺失门槛。
- Decisions：
- Remaining In-Slice Work：
- Risks / Deviations：
- Head SHA：真实实现检查点；尚未完成时为 NOT SET。

若出现可复用经验，提供简短候选供 A 在 Slice 关闭时合并；不要求每个 Task 单独总结，不作为 PASS 门槛。

## B Review Result

```text
Reviewed: NOT SET
Decision: PENDING
Slice Required Outcomes all satisfied: PENDING
Next: PENDING
```

审查只返回 PASS 或 FIX REQUIRED。通过后重新检查全部 RO，选择 NEXT TASK 或 SLICE READY FOR A REVIEW；不能在此关闭 Slice。
