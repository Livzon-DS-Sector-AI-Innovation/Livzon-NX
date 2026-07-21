import { fetchOffboardingRecords } from '@/actions/hr'
import { OffboardingClient } from '@/components/hr'

export const dynamic = 'force-dynamic'

export default async function OffboardingPage() {
  const res = await fetchOffboardingRecords({ page: 1, page_size: 20 })

  return (
    <OffboardingClient
      initialRecords={res.data}
      initialTotal={res.meta?.total || 0}
    />
  )
}
