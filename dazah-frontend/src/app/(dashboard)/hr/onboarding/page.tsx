import { fetchOnboardingRecords } from '@/actions/hr'
import { OnboardingClient } from '@/components/hr'

export const dynamic = 'force-dynamic'

export default async function OnboardingPage() {
  const res = await fetchOnboardingRecords({ page: 1, page_size: 20 })

  return (
    <OnboardingClient
      initialRecords={res.data}
      initialTotal={res.meta?.total || 0}
    />
  )
}
