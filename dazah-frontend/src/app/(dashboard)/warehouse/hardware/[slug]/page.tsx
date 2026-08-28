import { notFound } from 'next/navigation'
import { WarehouseFeishuTablePage } from '@/components/warehouse'
import { fetchWarehouseMaterialPage } from '@/lib/api/server/warehouse'
import { warehouseHardwarePageMap } from '@/lib/warehouse-hardware-pages'
import { resolveWarehousePageQueryParams, type WarehousePageProps } from '@/lib/warehouse-page-query'
import type { WarehouseFeishuMaterialPageData } from '@/types/warehouse'

export const dynamic = 'force-dynamic'

interface HardwarePageProps extends WarehousePageProps {
  params: Promise<{ slug: string }>
}

function createEmptyPageData(pageKey: string, pageTitle: string): WarehouseFeishuMaterialPageData {
  return {
    page_key: pageKey,
    page_title: pageTitle,
    table_name: pageTitle,
    columns: [],
    rows: [],
    total: 0,
    page: 1,
    page_size: 200,
    last_sync_time: '',
    source: 'feishu_bitable',
  }
}

export default async function WarehouseHardwarePage({ params, searchParams }: HardwarePageProps) {
  const { slug } = await params
  const definition = warehouseHardwarePageMap.get(slug)

  if (!definition) {
    notFound()
  }

  let data = createEmptyPageData(definition.pageKey, definition.label)

  try {
    data = await fetchWarehouseMaterialPage(definition.pageKey, {
      ...(await resolveWarehousePageQueryParams(searchParams)),
    }, 8000)
  } catch (error) {
    console.warn(`${definition.label} 页面初始数据加载失败，使用空数据降级:`, error)
  }

  return <WarehouseFeishuTablePage data={data} pageKey={definition.pageKey} />
}
