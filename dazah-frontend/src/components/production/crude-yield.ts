// 粗提工段收率口径（2026-11-10 业务确认）：
// 尚未产出粗品的批次（在产/待产）不参与收率统计——
// 趋势图留空、平均收率剔除、粗品累计收率分子分母同步剔除。

export type CrudeYieldRow = {
  total_input?: number | null
  crude_product_qty?: number | null
  yield_rate?: number | null
}

/** 批次是否已产出粗品（产品量为正数）。 */
export function hasCrudeOutput(
  crudeProductQty: number | null | undefined,
): boolean {
  return crudeProductQty != null && crudeProductQty > 0
}

/** 未产出批次的收率置空（趋势图留空、均值剔除），已产出批次原样保留。 */
export function applyCrudeYieldScope<T extends CrudeYieldRow>(rows: T[]): T[] {
  return rows.map((row) => ({
    ...row,
    yield_rate: hasCrudeOutput(row.crude_product_qty) ? row.yield_rate ?? null : null,
  }))
}

/** 粗品累计收率（%）：仅统计已产出批次，无产出时返回 null。 */
export function crudeCumulativeYieldPercent(rows: CrudeYieldRow[]): number | null {
  let totalIn = 0
  let totalOut = 0
  for (const row of rows) {
    if (!hasCrudeOutput(row.crude_product_qty)) continue
    if (row.total_input != null) totalIn += row.total_input
    totalOut += row.crude_product_qty ?? 0
  }
  return totalIn > 0 ? Math.round((totalOut / totalIn) * 1000) / 10 : null
}
