import { getServerApiBaseUrl } from '@/lib/server-api'
import { DeviationReportRecordPage } from '@/components/quality'
import type { FeishuDeviationReportRecordItem } from '@/types/quality'

export const dynamic = 'force-dynamic'

const API_BASE_URL = getServerApiBaseUrl()

async function getInitialReportRecords(): Promise<{
  items: FeishuDeviationReportRecordItem[]
  loadError: string | null
}> {
  try {
    const response = await fetch(
      `${API_BASE_URL}/api/v1/quality/deviation-report-records?page=1&page_size=50`,
      { cache: 'no-store' },
    )
    if (!response.ok) {
      throw new Error(`请求失败: ${response.status} ${response.statusText}`)
    }
    const json = await response.json()
    const data = json?.data
    const items = Array.isArray(data) ? data : Array.isArray(data?.items) ? data.items : []
    return {
      items,
      loadError: null,
    }
  } catch (error) {
    return {
      items: [],
      loadError: error instanceof Error ? error.message : '加载报告记录失败',
    }
  }
}

export default async function DeviationRecordsPage() {
  const { items, loadError } = await getInitialReportRecords()
  return <DeviationReportRecordPage initialItems={items} initialLoadError={loadError} />
}
