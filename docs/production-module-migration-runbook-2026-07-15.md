# 生产模块历史数据迁移运行手册

> 适用代码：`dazah-backend/scripts/production_migration.py`
>
> 当前边界：用户暂时跳过业务交接单；本手册和工具已完成，真实导入必须等源库导出、附件和字段映射到位后执行。

## 1. 已支持的数据实体

| 输入文件 | 目标业务 | 幂等依据 |
| --- | --- | --- |
| `batches.json` | 生产批次 | 来源系统 + 来源记录 ID + 内容指纹 |
| `production_execution_plans.json` | 车间日生产执行计划 | 同上 |
| `sales_plan_details.json` | 产销执行明细 | 来源系统 + 来源记录 ID + 内容指纹 |
| `process_execution_records.json` | 203 车间 13 工序 | 同上 |
| `fermentation_records.json` | 发酵记录 | 同上 |
| `seed_culture_records.json` | 种子培养 | 同上 |
| `non_conforming_events.json` | 非保密事件 | 迁移映射表 |
| `shift_logs.json` | 班次运行摘要 | 迁移映射表 |
| `shift_handovers.json` | 班组交接确认 | 迁移映射表 |

不存在的文件按零条处理，因此可以分实体、分车间、分批次逐步切换。

## 2. 输入格式

每个文件可以直接使用数组，也可以使用 `{ "records": [...] }`。每条数据必须包含稳定的来源记录 ID 和业务数据：

```json
{
  "records": [
    {
      "source_record_id": "source-primary-key-001",
      "data": {
        "batch_no": "F-20260715-001",
        "product_name": "L-苯丙氨酸",
        "fermenter": "F-01",
        "entry_date": "2026-07-15",
        "cycle_data": { "cycle_1": 12.5 },
        "status": "in_progress"
      }
    }
  ]
}
```

业务字段以当前 OpenAPI 中对应的 `*Create` Schema 为准。时间使用 ISO 8601，日期使用 `YYYY-MM-DD`；种子培养明细分别放入 `materials`、`quality_data`、`operation_data`。

## 3. 强制执行顺序

在 `dazah-backend` 目录执行：

```powershell
uv run python scripts/production_migration.py validate --input-dir <导出目录>
uv run python scripts/production_migration.py dry-run --input-dir <导出目录> --source-system production-module --run-key <唯一演练号>
uv run python scripts/production_migration.py import --input-dir <导出目录> --source-system production-module --run-key <唯一导入号>
uv run python scripts/production_migration.py reconcile --source-system production-module
```

执行约束：

1. `validate` 有任何错误时禁止继续。
2. `dry-run` 的失败数必须为 0，输入计数必须与源端导出计数一致。
3. 正式 `import` 前备份目标库，并冻结同一业务范围的人工写入。
4. 同一 `run-key` 重复执行会返回原运行结果；同一来源记录内容不变会计入 `skipped`，内容改变才会更新。
5. 对账中的 `missing_targets` 必须为 0；否则禁止扩大灰度范围。

## 4. 对账与异常处理

数据库中保留三层证据：

- `production.migration_runs`：每次校验后导入/演练的输入计数、结果计数和错误摘要。
- `production.migration_record_maps`：来源记录与平台记录的一一映射及 SHA-256 内容指纹。
- `production.migration_changes`：每次新增/更新的前值、前后指纹和回滚状态。

记录级数据库错误使用保存点隔离，一条失败不会把已经验证的其他记录变成未知状态；运行结果会标记 `completed_with_errors`，必须修复输入后使用新的运行号再次演练。

## 5. 回滚

仅正式 `import` 运行可回滚：

```powershell
uv run python scripts/production_migration.py rollback --run-id <正式导入运行 UUID> --run-key <唯一回滚号>
```

新增记录会软删除，更新记录会恢复导入前快照；回滚本身也会生成运行批次和变更状态。回滚后必须再次执行 `reconcile`，并由业务人员抽查批次、产量、事件和交接记录。

## 6. 灰度批次

真实交接物到位后的建议顺序：

1. 隔离测试库，全实体演练和逐表计数。
2. 203 车间单日数据，只读核验。
3. 203 车间单周数据，开放平台写入，源端切只读。
4. 全量历史数据，保留源端只读回查窗口。
5. 对账签字完成后关闭旧模块写入；附件另按清单核对哈希和缺失项。

## 7. 2026-07-15 空数据演练结果

- `validate`：9 个实体输入均为 0，错误 0。
- `dry-run`：运行号 `4407f004-8186-4725-88b7-daccc55f6c97`，状态 `dry_run_complete`，新增/更新/跳过/失败均为 0。
- 参考目录未提供命名业务 JSON，也未提供 CSV/XLSX 或源库导出，因此本次只能验证迁移链路，不能完成真实历史数据对账与导入。
- 专项自动化：覆盖空导入、重复来源 ID 拒绝、内容幂等和按运行批次回滚；仅在独立测试库执行合成数据，不写入业务库。
