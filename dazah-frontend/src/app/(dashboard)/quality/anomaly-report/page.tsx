import { FinishedProductAnomalyDashboard, QualityQueryProvider } from '@/components/quality'

export default function QualityAnomalyReportDashboardPage() {
  return (
    <QualityQueryProvider>
      <FinishedProductAnomalyDashboard />
    </QualityQueryProvider>
  )
}
