'use client'

import { useQuery } from '@tanstack/react-query'
import { InspectionFeishuTable, type FilterConfig } from './InspectionFeishuTable'
import { fetchItemsInventoryFilterOptions } from '@/lib/api/client/quality'

/**
 * 关键物资库存台账：读本地镜像、展示全部列，筛选/分类下拉项从镜像去重值动态生成。
 */
export function ItemsInventoryTable() {
  const { data } = useQuery({
    queryKey: ['quality-items', 'filter-options'],
    queryFn: fetchItemsInventoryFilterOptions,
  })

  const toOptions = (values: string[] | undefined) =>
    (values ?? []).map((v) => ({ label: v, value: v }))

  const filters: FilterConfig[] = [
    { key: '存放位置', label: '存放位置（分类）', type: 'select', options: toOptions(data?.['存放位置']) },
    { key: '库存报警', label: '库存报警', type: 'select', options: toOptions(data?.['库存报警']) },
  ]

  return (
    <InspectionFeishuTable
      title="关键物资库存"
      listApi="/api/v1/quality/items/inventory"
      pullApi="/api/v1/quality/items/inventory/pull"
      entityCode="qc_items_inventory"
      filters={filters}
      editable
    />
  )
}
