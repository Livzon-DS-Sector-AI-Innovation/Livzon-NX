/**
 * 仓储页面子领域分组（与后端 WAREHOUSE_EDIT_SCOPE_PERMISSION 一致）：
 * 成品 / 五金 / 原辅料及包材，用于前端编辑按钮的权限显隐（usePermission）。
 * 后端写端点按页面所属 Base 精校验为最终安全边界，此处仅体验层。
 */

export type WarehouseScope = "product" | "hardware" | "raw"

const RAW_PREFIXES = ["raw-", "packaging-", "inbound-ledger", "qualified-suppliers", "material-name-code-map"]

/** 页面 key → 子领域分组（与后端页面命名约定一致） */
export function warehouseScopeOf(pageKey: string): WarehouseScope {
  if (pageKey.startsWith("product-")) return "product"
  if (pageKey.startsWith("hardware-")) return "hardware"
  return "raw"
}

/** 子领域 → 细分编辑权限码 */
export function warehouseScopeWritePermission(scope: WarehouseScope): string {
  switch (scope) {
    case "product":
      return "warehouse:product:write"
    case "hardware":
      return "warehouse:hardware:write"
    default:
      return "warehouse:raw:write"
  }
}

/** 页面是否属于原辅料及包材分组（供无 pageKey 的场景判断） */
export function isRawScopePageKey(pageKey: string): boolean {
  return RAW_PREFIXES.some((p) => pageKey.startsWith(p))
}
