import {
  getEmergencyCardStats,
  getEmergencyCards,
} from '@/actions/safety'
import { EmergencyCardPanel } from '@/components/safety'

export const dynamic = 'force-dynamic'

const PAGE_NAME = '应急处置卡'

export default async function SafetyEmergencyCardPage() {
  const [statsRes, listRes] = await Promise.all([
    getEmergencyCardStats(),
    getEmergencyCards({ page: 1, page_size: 20 }),
  ])
  const stats = statsRes.code === 200 && statsRes.data ? statsRes.data : null
  const cards = listRes.code === 200 && listRes.data ? listRes.data : null
  const initialError = cards
    ? null
    : listRes.message || '读取应急处置卡失败，请稍后重试或重新登录'

  return (
    <div style={{ padding: '0 0 24px' }}>
      <h2 style={{ marginBottom: 4 }}>{PAGE_NAME}</h2>
      <p style={{ marginBottom: 16, color: 'var(--color-text-secondary)' }}>
        收录各车间、岗位及公司级事故现场应急处置卡（101-102、103、201 一车间、203
        车间、动力部等），内容与纸质处置卡一致：处置步骤、负责人、应急电话、主要风险与注意事项。
      </p>
      <EmergencyCardPanel
        initialStats={stats}
        initialCards={cards}
        initialError={initialError}
      />
    </div>
  )
}
