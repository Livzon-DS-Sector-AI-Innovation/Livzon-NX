import { WarehouseFeishuTablePage } from '@/components/warehouse'
import { fetchWarehouseMaterialPage } from '@/lib/api/server/warehouse'
import { resolveWarehousePageQueryParams, type WarehousePageProps } from '@/lib/warehouse-page-query'
import type { WarehouseFeishuMaterialPageData } from '@/types/warehouse'

export const dynamic = 'force-dynamic'

function createEmptyPageData(): WarehouseFeishuMaterialPageData {
  return {
    page_key: 'qualified-suppliers',
    page_title: '原辅材料合格供应商一览表',
    table_name: '原辅材料合格供应商一览表',
    columns: [],
    rows: [],
    total: 0,
    page: 1,
    page_size: 200,
    last_sync_time: '',
    source: 'feishu_bitable',
  }
}

export default async function WarehouseQualifiedSuppliersPage({ searchParams }: WarehousePageProps) {
  let data = createEmptyPageData()

  try {
    data = await fetchWarehouseMaterialPage(
      'qualified-suppliers',
      await resolveWarehousePageQueryParams(searchParams), 8000
    )
  } catch (error) {
    console.warn('原辅材料合格供应商一览表页面初始数据加载失败，使用空数据降级:', error)
  }

  return <WarehouseFeishuTablePage data={data} pageKey="qualified-suppliers" />
}
