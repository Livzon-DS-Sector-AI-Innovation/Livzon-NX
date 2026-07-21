import { fetchReferenceStandardsServer } from '@/actions/registration'
import ReferenceStandardClient from '@/components/registration/ReferenceStandardClient'

export const dynamic = 'force-dynamic'

export default async function ReferenceStandardPage() {
  const recordsRes = await fetchReferenceStandardsServer({ page: 1, page_size: 20 })

  return (
    <ReferenceStandardClient
      initialRecords={recordsRes?.data || []}
      initialTotal={recordsRes?.meta?.total || 0}
    />
  )
}
