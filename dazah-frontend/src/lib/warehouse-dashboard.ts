import type {
  WarehouseDashboardData,
  WarehouseDashboardGroup,
  WarehouseDashboardNameValue,
  WarehouseDashboardTrendPoint,
  WarehouseDashboardDeptValue,
} from '@/types/warehouse'

type UnknownRecord = Record<string, unknown>

function asRecord(value: unknown): UnknownRecord {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as UnknownRecord)
    : {}
}

function numberValue(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : Number(value || 0)
}

function arrayValue<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : []
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {}
}

/**
 * 将后端/旧接口的空或部分响应归一为页面可安全渲染的结构。
 * 迁移期间部分旧数据源可能返回空数组 envelope，页面仍必须显示空状态而不是崩溃。
 */
export function normalizeWarehouseDashboard(
  group: WarehouseDashboardGroup,
  value: unknown,
): WarehouseDashboardData {
  const source = asRecord(value)

  if (group === 'raw') {
    const safety = asRecord(source.safety)
    const quality = asRecord(source.quality)
    return {
      safety: {
        total: numberValue(safety.total),
        ok: numberValue(safety.ok),
        low: numberValue(safety.low),
      },
      quality: {
        合格: numberValue(quality['合格']),
        待验: numberValue(quality['待验']),
        不合格: numberValue(quality['不合格']),
      },
      material_outbound_30d: arrayValue<WarehouseDashboardTrendPoint>(source.material_outbound_30d),
      packaging_outbound_30d_total: numberValue(source.packaging_outbound_30d_total),
      month_inbound_total: numberValue(source.month_inbound_total),
      low_stock_top: arrayValue(source.low_stock_top),
      detail: objectValue(source.detail) as never,
    }
  }

  if (group === 'hardware') {
    return {
      stock_amount: numberValue(source.stock_amount),
      dept_stock: arrayValue<WarehouseDashboardDeptValue>(source.dept_stock),
      inbound_30d_total: numberValue(source.inbound_30d_total),
      outbound_30d_total: numberValue(source.outbound_30d_total),
      outbound_30d_trend: arrayValue<WarehouseDashboardTrendPoint>(source.outbound_30d_trend),
      dept_outbound_30d: arrayValue<WarehouseDashboardDeptValue>(source.dept_outbound_30d),
      detail: objectValue(source.detail) as never,
    }
  }

  return {
    qualified: numberValue(source.qualified),
    pending: numberValue(source.pending),
    pending_batches: numberValue(source.pending_batches),
    product_stock: arrayValue<WarehouseDashboardNameValue>(source.product_stock),
    product_outbound: arrayValue<WarehouseDashboardNameValue>(source.product_outbound),
    // 旧仓储仪表盘使用 product_pending/product_qualified 字段，保留两者的兼容映射。
    product_pending: arrayValue<WarehouseDashboardNameValue>(source.product_pending),
    product_qualified: arrayValue<WarehouseDashboardNameValue>(source.product_qualified),
    shipping_30d_trend: arrayValue<WarehouseDashboardTrendPoint>(source.shipping_30d_trend),
    product_monthly_inbound: objectValue(source.product_monthly_inbound) as never,
    product_monthly_outbound: objectValue(source.product_monthly_outbound) as never,
    zero_activity_products: arrayValue<string>(source.zero_activity_products),
    detail: objectValue(source.detail) as never,
  } as WarehouseDashboardData
}
