# Task [ID] — [一个完整实施目标]

模板受当前 [Slice](../SLICE.md) 约束，执行顺序见 [开发流程](../docs/development-workflow.md)。复制到根 TASK.md 时将链接改为根目录相对路径。

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

记录准确的聚焦／相关／质量命令与实机门槛。T4 包含已有完整回归及高风险边界；其他等级按实际影响确定。不得列出不存在项目的“已通过”命令。

## 非目标

列出下一个 Task／Slice、生成程序、代理改动和不需要的重构等明确排除项。

## Developer Completion Report

- Changed Files：
- Implemented：
- Tests and Results：
- Decisions：
- Remaining In-Slice Work：
- Risks / Deviations：
- Head SHA：真实实现检查点；尚未完成时为 NOT SET。

## B Review Result

```text
Reviewed: NOT SET
Decision: PENDING
Slice Required Outcomes all satisfied: PENDING
Next: PENDING
```

审查只返回 PASS 或 FIX REQUIRED。通过后重新检查全部 RO，选择 NEXT TASK 或 SLICE READY FOR A REVIEW；不能在此关闭 Slice。
