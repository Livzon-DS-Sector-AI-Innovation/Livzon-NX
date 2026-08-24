import { fetchContractsServer } from '@/lib/api/server/hr'
import ContractTableClient from '@/components/hr/ContractTableClient'

export const dynamic = 'force-dynamic'

export default async function ContractsPage() {
  const res = await fetchContractsServer({ page: 1, page_size: 50 })
  // res.data is { data: [...], total, page, page_size }
  const contracts = res.data?.data || []
  const total = res.data?.total || 0

  return <ContractTableClient initialData={contracts} initialTotal={total} />
}
