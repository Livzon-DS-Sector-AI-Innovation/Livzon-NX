import { ContractSummaryClient } from '@/components/purchasing'
import { fetchContractRecords } from '@/lib/api/purchasing'
import { getAuthHeaders } from '@/lib/auth'
import type { ContractRecordResponse } from '@/types/purchasing'

export const dynamic = 'force-dynamic'

const DEFAULT_PAGE_SIZE = 12

export default async function ContractSummaryPage() {
  let records: ContractRecordResponse[] = []
  let total = 0
  let initialLoadFailed = false

  try {
    const response = await fetchContractRecords({
      page: 1,
      page_size: DEFAULT_PAGE_SIZE,
    }, await getAuthHeaders())
    records = response.data ?? []
    total = Number(response.meta?.total ?? records.length)
  } catch {
    initialLoadFailed = true
  }

  return (
    <ContractSummaryClient
      initialRecords={records}
      initialTotal={Number.isFinite(total) ? total : records.length}
      initialLoadFailed={initialLoadFailed}
    />
  )
}
