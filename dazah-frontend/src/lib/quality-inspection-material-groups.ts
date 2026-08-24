export const solidInspectionGroups = [
  { key: 'ys-000', label: 'YS000' },
  { key: 'ys-100', label: 'YS100' },
  { key: 'ys-200', label: 'YS200' },
  { key: 'ys-300', label: 'YS300' },
  { key: 'ys-400', label: 'YS400' },
  { key: 'ys-500', label: 'YS500' },
  { key: 'ys-600', label: 'YS600' },
  { key: 'ys-700', label: 'YS700' },
  { key: 'ys-800', label: 'YS800' },
  { key: 'manual', label: '待人工归组' },
] as const

export const liquidInspectionGroups = [
  { key: 'yl-0xx', label: 'YL0xx' },
  { key: 'yl-1xx', label: 'YL1xx' },
  { key: 'yl-2xx', label: 'YL2xx' },
  { key: 'yl-3xx', label: 'YL3xx' },
  { key: 'yl-4xx', label: 'YL4xx' },
  { key: 'yl-5xx', label: 'YL5xx' },
  { key: 'yl-6xx', label: 'YL6xx' },
  { key: 'yl-7xx', label: 'YL7xx' },
  { key: 'yl-8xx', label: 'YL8xx' },
] as const

export function getSolidInspectionGroupLabel(group: string) {
  return solidInspectionGroups.find((item) => item.key === group)?.label
}

export function getLiquidInspectionGroupLabel(group: string) {
  return liquidInspectionGroups.find((item) => item.key === group)?.label
}
