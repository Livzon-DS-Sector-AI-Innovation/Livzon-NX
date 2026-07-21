export interface BatchProductionLineGroup {
  key: string
  label: string
  codes: string[]
}

export const BATCH_PRODUCTION_LINE_GROUPS: BatchProductionLineGroup[] = [
  { key: "strain", label: "菌种", codes: ["101-1"] },
  { key: "fermentation", label: "发酵", codes: ["101-2", "102-1", "103-1", "103-2"] },
  {
    key: "extraction",
    label: "提炼",
    codes: ["102-2", "201-1", "201-2", "203", "201-3", "202", "203-3"],
  },
]

export const STRAIN_BATCH_PRODUCT_NAMES = [
  "多拉菌素",
  "盐酸林可霉素",
  "苯丙氨酸",
  "洛伐他汀",
  "美伐他汀",
]

export const BATCH_PRODUCT_NAMES = [
  "多拉菌素",
  "L-苯丙氨酸",
  "盐酸林可霉素",
  "洛伐他汀",
  "美伐他汀",
  "霉酚酸",
]

export function getBatchProductionLinePath(code: string): string {
  return `/production/batches?production_line=${encodeURIComponent(code)}`
}

export function getBatchProductPath(productName: string): string {
  return `/production/batches?product_name=${encodeURIComponent(productName)}`
}

export function getBatchProductionLineMeta(code?: string | null): {
  groupLabel: string
  code: string
} | null {
  if (!code) return null

  for (const group of BATCH_PRODUCTION_LINE_GROUPS) {
    if (group.codes.includes(code)) {
      return { groupLabel: group.label, code }
    }
  }

  return null
}
