import { DeviationInvestigationPushPage, QualityQueryProvider } from '@/components/quality'

export default function DeviationInvestigationsPage() {
  return (
    <QualityQueryProvider>
      <DeviationInvestigationPushPage />
    </QualityQueryProvider>
  )
}
