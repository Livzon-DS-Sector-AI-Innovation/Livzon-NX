import { fetchDepartureRecords } from '@/actions/hr'
import { DepartureClient } from '@/components/hr'

export const dynamic = 'force-dynamic'

export default async function DeparturePage() {
  const res = await fetchDepartureRecords({ page: 1, page_size: 20 })

  return (
    <DepartureClient
      initialRecords={res.data}
      initialTotal={res.meta?.total || 0}
    />
  )
}
