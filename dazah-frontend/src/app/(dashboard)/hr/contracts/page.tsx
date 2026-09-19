import { fetchContractsServer } from '@/lib/api/server/hr'
import ContractTableClient from '@/components/hr/ContractTableClient'

export const dynamic = 'force-dynamic'

export default async function ContractsPage() {
  let contracts: any[] = []
  let total = 0

  try {
    const res = await fetchContractsServer({ page: 1, page_size: 50 })
    // res.data is { data: [...], total, page, page_size }
    contracts = res.data?.data || []
    total = res.data?.total || 0
  } catch {
    // 后端不可用时使用空数据初始化，客户端会自动重试
  }

  return <ContractTableClient initialData={contracts} initialTotal={total} />
}
