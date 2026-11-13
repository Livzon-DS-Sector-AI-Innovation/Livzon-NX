import { getGuardianRoster } from '@/actions/safety'
import { GuardianRosterPanel } from '@/components/safety/GuardianRosterPanel'

export const dynamic = 'force-dynamic'

export const metadata = {
  title: '监护人名单 | 安全管理',
}

export default async function SafetyGuardianRosterPage() {
  const pageKey = 'safety:ops-safety:guardian-roster'
  const listRes = await getGuardianRoster({ pageKey, page: 1, pageSize: 20 })
  const list = listRes.code === 200 && listRes.data ? listRes.data : null
  const initialError =
    listRes.code === 200 ? null : (listRes.message ?? '监护人名单加载失败')

  return (
    <div style={{ padding: 24 }}>
      <GuardianRosterPanel initialList={list as never} initialError={initialError} />
    </div>
  )
}
