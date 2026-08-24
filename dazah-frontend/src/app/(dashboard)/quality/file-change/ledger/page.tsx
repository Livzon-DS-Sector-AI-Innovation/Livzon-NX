import { FileChangePage, QualityQueryProvider } from '@/components/quality'

export const dynamic = 'force-dynamic'

export default function FileChangeLedgerPage() {
  return (
    <QualityQueryProvider>
      <FileChangePage />
    </QualityQueryProvider>
  )
}
