# 设备模块 ↔ 采购模块 备件采购契约（待 Owner 评审）

> 版本 v1 · 2026-11-04 · 状态：**待采购 Owner 评审**
> 背景：设备模块方案C「备件采购联动」；代码已上线开发环境并通过 E2E（真实生成采购草稿单验证）。

## 一、契约 1：设备 → 采购（提交采购申请）

```python
# app/modules/procurement/public_api.py
async def create_equipment_purchase_request(
    db: AsyncSession,
    *,
    items: list[dict],                    # 见下方字段
    request_department: str = "设备动力部",
    attachment_note: str = "设备模块备件安全线预警自动生成",
) -> dict  # {request_id: str, total_amount: float, status: str}
```

**items 字段**：`product_name`（必填）、`specification`、`material_code`（备件编码，五金类必填）、`quantity`、`unit`、`unit_price`、`remarks`。`material_description` 缺省时自动用「名称 规格」补齐（采购侧校验必填）。

**行为承诺**：
- 只创建 **draft 状态**采购申请单（五金类），审批/供应商/下单全流程留在采购模块，设备侧零侵入；
- 单条失败不影响同批其他条（设备侧逐条调用、逐条捕获）；
- 返回 `request_id` 由设备侧回填 `spare_part_purchase_suggestions.purchase_request_id` 供追溯。

**评审要点**（请 Owner 确认）：
1. 分类固定 `hardware`、部门固定「设备动力部」是否符合采购口径；
2. 设备侧是否需要在采购申请上携带更多字段（预算科目/紧急度/链接）；
3. 采购模块删除草稿单后，设备侧建议仍为 submitted——是否需要状态回传（当前不回传，人工在设备页取消即可）。

## 二、契约 2：采购 → 设备（到货回写，预留）

```python
# app/modules/equipment/public_api.py
async def spare_part_purchase_arrived(
    db: AsyncSession,
    *,
    suggestion_id: uuid.UUID,
    arrived_qty: int,
    operator_id: uuid.UUID | None = None,
) -> dict  # {suggestion_id, arrived_qty, status}
```

**行为**：执行备件入库（写 stocks+transactions）并推进建议状态（partial/done）。

**当前状态**：设备页「登记到货」按钮已用此逻辑人工闭环；**自动接入尚未发生**。采购到货自动化（或到货事件流）就绪后，在到货处理处按 `purchase_request_id` 反查建议表调用本函数即可。**幂等由调用方保证**（如以采购到货事件 ID 去重后调用）。

## 三、验证记录（2026-11-04 E2E）

- 真实链路生成草稿单 ×2（¥1350/9套@¥150），明细、部门、分类正确；
- 提交-到货-入库-状态推进全链路通过；采购模块全量测试 0 回归。

## 四、回滚

设备侧功能开关：停止 `equipment.spare_part_purchase_scan` 调度 + 隐藏前端「采购建议」Tab 即可；采购侧封装函数无状态、无表结构变更，可安全保留或移除。
