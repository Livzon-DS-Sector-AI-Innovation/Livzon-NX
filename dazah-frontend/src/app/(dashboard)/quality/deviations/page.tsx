import { DeviationDashboardPage, QualityQueryProvider } from '@/components/quality'

export default function DeviationsPage() {
  return (
    <QualityQueryProvider>
      <DeviationDashboardPage />
    </QualityQueryProvider>
  )
}
