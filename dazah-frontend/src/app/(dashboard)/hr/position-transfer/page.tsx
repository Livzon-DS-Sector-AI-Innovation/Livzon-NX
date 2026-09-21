import { fetchPositionTransfersServer } from '@/lib/api/server/hr'
import { PositionTransferClient } from '@/components/hr'

export const dynamic = 'force-dynamic'

export default async function PositionTransferPage() {
  let initialRecords: any[] = []
  let initialTotal = 0

  try {
    const res = await fetchPositionTransfersServer({ page: 1, page_size: 20 })
    initialRecords = res.data || []
    initialTotal = res.meta?.total || 0
  } catch {
    // 后端不可用时使用空数据初始化，客户端会自动重试
  }

  return (
    <PositionTransferClient
      initialRecords={initialRecords}
      initialTotal={initialTotal}
    />
  )
}
