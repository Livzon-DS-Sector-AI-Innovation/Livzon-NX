import {
  getCommitmentCards,
  getCommitmentToday,
} from '@/actions/safety'
import { SafetyCommitmentPanel } from '@/components/safety'
import { SAFETY_COMMITMENT_PAGE_KEY } from '@/lib/safety-commitment'

export const dynamic = 'force-dynamic'

export const metadata = {
  title: '安全承诺 | 安全管理',
}

export default async function SafetyCommitmentPage() {
  const [todayRes, cardsRes] = await Promise.all([
    getCommitmentToday(SAFETY_COMMITMENT_PAGE_KEY),
    getCommitmentCards(undefined, SAFETY_COMMITMENT_PAGE_KEY),
  ])
  const today =
    todayRes.code === 200 && todayRes.data ? todayRes.data : null
  const cards =
    cardsRes.code === 200 && cardsRes.data ? cardsRes.data.cards : []
  const initialError =
    todayRes.code === 200
      ? null
      : (todayRes.message ?? '安全承诺日报加载失败')

  return (
    <div style={{ padding: 24 }}>
      <SafetyCommitmentPanel
        initialReport={today?.report ?? null}
        initialCreatedToday={today?.created_today ?? false}
        initialCards={cards}
        initialError={initialError}
      />
    </div>
  )
}
