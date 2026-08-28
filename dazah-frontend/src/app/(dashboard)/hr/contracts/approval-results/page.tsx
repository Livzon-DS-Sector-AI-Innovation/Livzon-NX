import { fetchContractApprovalResultsServer } from '@/lib/api/server/hr'
import ContractApprovalResultsClient from '@/components/hr/ContractApprovalResultsClient'

export const dynamic = 'force-dynamic'

function currentQuarterRange(): { start: string; end: string } {
  const now = new Date()
  const q = Math.floor(now.getMonth() / 3)
  const start = new Date(now.getFullYear(), q * 3, 1)
  const end = new Date(now.getFullYear(), q * 3 + 3, 0)
  const fmt = (d: Date) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  return { start: fmt(start), end: fmt(end) }
}

export default async function ContractApprovalResultsPage() {
  const { start, end } = currentQuarterRange()
  const res = await fetchContractApprovalResultsServer({
    start_date: start,
    end_date: end,
    page: 1,
    page_size: 20,
  }).catch(() => null)
  const data = res?.data || []
  const total = res?.meta?.total || 0

  return (
    <ContractApprovalResultsClient
      initialData={data}
      initialTotal={total}
      initialStartDate={start}
      initialEndDate={end}
    />
  )
}
