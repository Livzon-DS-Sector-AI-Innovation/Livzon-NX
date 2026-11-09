import { getWorkPermitStats, getWorkPermits } from '@/actions/safety'
import { WorkPermitListPanel } from '@/components/safety'

export const dynamic = 'force-dynamic'

export const metadata = {
  title: '作业票审批 | 安全管理',
}

export default async function SafetyWorkPermitsPage() {
  const [listRes, statsRes] = await Promise.all([
    getWorkPermits({
      pageKey: 'safety:ops-safety:work-permits',
      page: 1,
      pageSize: 20,
    }),
    getWorkPermitStats('safety:ops-safety:work-permits'),
  ])
  const list = listRes.code === 200 && listRes.data ? listRes.data : null
  const stats = statsRes.code === 200 && statsRes.data ? statsRes.data : null
  const initialError =
    listRes.code === 200 ? null : (listRes.message ?? '作业票列表加载失败')

  return (
    <div style={{ padding: 24 }}>
      <WorkPermitListPanel
        initialList={list as never}
        initialStats={stats as never}
        initialError={initialError}
      />
    </div>
  )
}
