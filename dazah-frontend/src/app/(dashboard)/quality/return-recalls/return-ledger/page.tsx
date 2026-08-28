import { ReturnLedgerPage } from '@/components/quality'
import { QualityQueryProvider } from '@/components/quality'
import type { ReturnLedgerItem } from '@/types/quality'
import { fetchReturnLedgerServer } from '@/lib/api/server/quality'

export const dynamic = 'force-dynamic'

export default async function Page() {
  const initialItems: ReturnLedgerItem[] = await fetchReturnLedgerServer()
  return (
    <QualityQueryProvider>
      <ReturnLedgerPage initialItems={initialItems} />
    </QualityQueryProvider>
  )
}
