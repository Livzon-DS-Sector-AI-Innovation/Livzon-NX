import { ChangePage, QualityQueryProvider } from '@/components/quality'

export default function ChangeLedgerPage() {
  return (
    <QualityQueryProvider>
      <ChangePage />
    </QualityQueryProvider>
  )
}
