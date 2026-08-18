import {
  PurchaseRequestFormClient,
  purchaseCategoryLabels,
} from '@/components/purchasing'
import { fetchPurchaseRequests } from '@/lib/api/purchasing'
import { getAuthHeaders } from '@/lib/auth'

export const dynamic = 'force-dynamic'

const DEFAULT_PAGE_SIZE = 20

export default async function UrgentPurchaseRequestPage() {
  const response = await fetchPurchaseRequests(
    {
      category: 'urgent',
      page: 1,
      page_size: DEFAULT_PAGE_SIZE,
    },
    await getAuthHeaders()
  ).catch(() => null)
  const initialLoadFailed = response === null
  const initialResponse = response ?? {
    code: 200,
    message: 'success',
    data: [],
    meta: {
      page: 1,
      page_size: DEFAULT_PAGE_SIZE,
      total: 0,
    },
  }

  return (
    <PurchaseRequestFormClient
      category="urgent"
      categoryLabel={purchaseCategoryLabels.urgent}
      initialRequests={initialResponse.data}
      initialTotal={Number(initialResponse.meta?.total ?? initialResponse.data.length)}
      initialLoadFailed={initialLoadFailed}
    />
  )
}
