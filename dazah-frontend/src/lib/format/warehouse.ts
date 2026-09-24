import type { WarehouseRecordFieldValue } from '@/types/warehouse'

/** 记录详情字段的只读展示文本（空值/-、数组拼接、布尔转中文名）。 */
export function formatDetailDisplayValue(field: WarehouseRecordFieldValue): string {
  const value = field.value
  if (value === null || value === undefined || value === '') {
    return '-'
  }
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (typeof item === 'string') {
          return item
        }
        if (item && typeof item === 'object') {
          const obj = item as Record<string, unknown>
          return String(obj.name ?? obj.text ?? obj.id ?? obj.file_token ?? JSON.stringify(obj))
        }
        return String(item)
      })
      .join('、')
  }
  if (typeof value === 'boolean') {
    return value ? '是' : '否'
  }
  return String(value)
}
