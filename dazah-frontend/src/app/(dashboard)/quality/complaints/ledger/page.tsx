import { ComplaintLedgerPage } from '@/components/quality'
import { QualityQueryProvider } from '@/components/quality'
import type { ComplaintLedgerItem } from '@/types/quality'
import { fetchComplaintLedgerServer } from '@/lib/api/server/quality'

export const dynamic = 'force-dynamic'

export default async function Page() {
  const initialItems: ComplaintLedgerItem[] = await fetchComplaintLedgerServer()
  return (
    <QualityQueryProvider>
      <ComplaintLedgerPage initialItems={initialItems} />
    </QualityQueryProvider>
  )
}
