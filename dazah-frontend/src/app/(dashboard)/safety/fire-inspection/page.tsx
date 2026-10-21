import {
  getFireEquipmentList,
  getFireEquipmentStats,
  getFireInspectionRecords,
} from '@/actions/safety'
import { FireEquipmentPanel } from '@/components/safety'
import { SAFETY_PAGE_TABLE_KEYS } from '@/lib/safety-page-tables'

export const dynamic = 'force-dynamic'

const PAGE_NAME = '灭火器及消防栓点检'

export default async function SafetyFireInspectionPage() {
  const pageKey = SAFETY_PAGE_TABLE_KEYS.fireEquipmentInspection
  const [statsRes, listRes, recordsRes] = await Promise.all([
    getFireEquipmentStats({ pageKey }),
    getFireEquipmentList({ pageKey, page: 1, pageSize: 20 }),
    getFireInspectionRecords({ pageKey, page: 1, pageSize: 20 }),
  ])
  const stats = statsRes.code === 200 && statsRes.data ? statsRes.data : null
  const equipmentList =
    listRes.code === 200 && listRes.data ? listRes.data : null
  const records = recordsRes.code === 200 && recordsRes.data ? recordsRes.data : null
  const initialError =
    equipmentList
      ? null
      : listRes.message || '读取器材台账失败，请稍后重试或重新登录'

  return (
    <div style={{ padding: '0 0 24px' }}>
      <h2 style={{ marginBottom: 4 }}>{PAGE_NAME}</h2>
      <p style={{ marginBottom: 16, color: 'var(--color-text-secondary)' }}>
        台账来自飞书多维表格（各车间子表），每台器材可生成二维码；飞书扫码即可查看详情并按检查卡逐项点检（每月一次）。
      </p>
      <FireEquipmentPanel
        pageKey={pageKey}
        initialStats={stats}
        initialEquipment={equipmentList}
        initialRecords={records}
        initialError={initialError}
      />
    </div>
  )
}
