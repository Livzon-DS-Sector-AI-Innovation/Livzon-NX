import {
  getSafetyPageTableRecords,
  getSafetyPageTableStats,
} from '@/actions/safety'
import { PageFeishuTable } from '@/components/safety'
import {
  SAFETY_PAGE_TABLE_KEYS,
  toPageTableStats,
  toRecordRows,
} from '@/lib/safety-page-tables'

export const dynamic = 'force-dynamic'

const PAGE_NAME = '24小时值班隐患'

export default async function SafetyHazardDutyPage() {
  const pageKey = SAFETY_PAGE_TABLE_KEYS.hazardDuty
  const [res, statsRes] = await Promise.all([
    getSafetyPageTableRecords({ pageKey, page: 1, pageSize: 20 }),
    getSafetyPageTableStats({ pageKey }),
  ])
  const data = res.code === 200 && res.data ? res.data : null

  return (
    <div style={{ padding: '0 0 24px' }}>
      <h2 style={{ marginBottom: 16 }}>{PAGE_NAME}</h2>
      <PageFeishuTable
        pageKey={pageKey}
        pageName={PAGE_NAME}
        initialData={
          data
            ? {
                columns: data.columns ?? [],
                records: toRecordRows(data.records),
                total: data.total,
                page: data.page,
                page_size: data.page_size,
                truncated: data.truncated,
              }
            : null
        }
        initialStats={statsRes.code === 200 ? toPageTableStats(statsRes.data) : null}
        initialError={data ? null : res.message || '读取多维表格数据失败'}
      />
    </div>
  )
}
