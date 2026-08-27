import { fetchPositionTransfersServer } from '@/lib/api/server/hr'
import { PositionTransferClient } from '@/components/hr'

export const dynamic = 'force-dynamic'

export default async function PositionTransferPage() {
  const res = await fetchPositionTransfersServer({ page: 1, page_size: 20 })

  return (
    <PositionTransferClient
      initialRecords={res.data}
      initialTotal={res.meta?.total || 0}
    />
  )
}
