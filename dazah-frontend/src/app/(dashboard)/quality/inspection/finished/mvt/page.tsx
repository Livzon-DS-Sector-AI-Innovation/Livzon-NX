import { QualityQueryProvider } from '@/components/quality/QualityQueryProvider'
import { FinishedSubtablePage } from '@/components/quality/inspection/FinishedSubtablePage'
import { MvtTrendDashboard } from '@/components/quality/inspection/MvtTrendDashboard'

export const dynamic = 'force-dynamic'

export default function FinishedMvtPage() {
  return (
    <QualityQueryProvider>
      <FinishedSubtablePage
        title="美伐他汀"
        productGroup="mvt"
        dashboardContent={<MvtTrendDashboard />}
      />
    </QualityQueryProvider>
  )
}
