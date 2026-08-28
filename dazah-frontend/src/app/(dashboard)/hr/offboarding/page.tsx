import { fetchOffboardingRecords } from '@/actions/hr'
import { OffboardingClient } from '@/components/hr'

export const dynamic = 'force-dynamic'

export default async function OffboardingPage() {
  let initialRecords: any[] = []
  let initialTotal = 0

  try {
    const res = await fetchOffboardingRecords({ page: 1, page_size: 20 })
    initialRecords = res.data || []
    initialTotal = res.meta?.total || 0
  } catch {
    // 后端不可用时使用空数据初始化，客户端会自动重试
  }

  return (
    <OffboardingClient
      initialRecords={initialRecords}
      initialTotal={initialTotal}
    />
  )
}
