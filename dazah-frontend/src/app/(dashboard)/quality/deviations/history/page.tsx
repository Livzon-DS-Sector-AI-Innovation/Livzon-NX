import { DeviationHistoryPage, QualityQueryProvider } from '@/components/quality'

export default function DeviationHistoryPageShell() {
  return (
    <QualityQueryProvider>
      <DeviationHistoryPage />
    </QualityQueryProvider>
  )
}
