import { InspectionDashboardPage, InspectionQueryProvider } from '@/components/quality'

export const dynamic = 'force-dynamic'

export default function QualityInspectionPage() {
  return (
    <InspectionQueryProvider>
      <InspectionDashboardPage />
    </InspectionQueryProvider>
  )
}
