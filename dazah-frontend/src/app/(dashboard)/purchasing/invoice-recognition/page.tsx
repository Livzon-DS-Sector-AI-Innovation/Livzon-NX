import { InvoiceRecognitionClient, InvoiceRecognitionQueryProvider } from '@/components/purchasing'
import { fetchInvoiceRecognitionRecords } from '@/lib/api/purchasing'
import { getAuthHeaders } from '@/lib/auth'

export const dynamic = 'force-dynamic'

const DEFAULT_PAGE_SIZE = 20

export default async function InvoiceRecognitionPage() {
  let initialLoadFailed = false
  const recordsResponse = await fetchInvoiceRecognitionRecords({
    page: 1,
    page_size: DEFAULT_PAGE_SIZE,
  }, await getAuthHeaders()).catch(() => {
    initialLoadFailed = true
    return {
      code: 200,
      message: 'success',
      data: [],
      meta: {
        page: 1,
        page_size: DEFAULT_PAGE_SIZE,
        total: 0,
      },
    }
  })
  const initialTotal = Number(recordsResponse.meta?.total ?? recordsResponse.data.length)

  return (
    <InvoiceRecognitionQueryProvider>
      <InvoiceRecognitionClient
        initialRecords={recordsResponse.data}
        initialTotal={Number.isFinite(initialTotal) ? initialTotal : recordsResponse.data.length}
        initialLoadFailed={initialLoadFailed}
      />
    </InvoiceRecognitionQueryProvider>
  )
}
