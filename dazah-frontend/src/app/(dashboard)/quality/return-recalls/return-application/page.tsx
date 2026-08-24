import { ReturnApplicationPage } from '@/components/quality'
import { QualityQueryProvider } from '@/components/quality'
import type { ReturnApplicationItem } from '@/types/quality'
import { fetchReturnApplicationServer } from '@/lib/api/server/quality'

export const dynamic = 'force-dynamic'

export default async function Page() {
  const initialItems: ReturnApplicationItem[] = await fetchReturnApplicationServer()
  return (
    <QualityQueryProvider>
      <ReturnApplicationPage initialItems={initialItems} />
    </QualityQueryProvider>
  )
}
