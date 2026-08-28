import { WarehouseFeishuTablePage } from '@/components/warehouse'
import { fetchWarehouseMaterialPage } from '@/lib/api/server/warehouse'
import { resolveWarehousePageQueryParams, type WarehousePageProps } from '@/lib/warehouse-page-query'
import type { WarehouseFeishuMaterialPageData } from '@/types/warehouse'

export const dynamic = 'force-dynamic'

function createEmptyPageData(): WarehouseFeishuMaterialPageData {
  return {
    page_key: 'product-detail-demeclocycline-hcl',
    page_title: '盐酸去甲金霉素库存明细',
    table_name: '盐酸去甲金霉素库存明细',
    columns: [],
    rows: [],
    total: 0,
    page: 1,
    page_size: 200,
    last_sync_time: '',
    source: 'feishu_bitable',
  }
}

export default async function WarehouseProductDemeclocyclineHclPage({
  searchParams,
}: WarehousePageProps) {
  let data = createEmptyPageData()

  try {
    data = await fetchWarehouseMaterialPage('product-detail-demeclocycline-hcl', {
      ...(await resolveWarehousePageQueryParams(searchParams))
    })
  } catch (error) {
    console.warn('盐酸去甲金霉素库存明细页面初始数据加载失败，使用空数据降级:', error)
  }

  return <WarehouseFeishuTablePage data={data} pageKey='product-detail-demeclocycline-hcl' />
}
