import { QualityQueryProvider } from '@/components/quality'
import { MaintenanceRecordsPage } from '@/components/quality/inspection'

export const dynamic = 'force-dynamic'

export default function InstrMaintenancePage() {
  return (
    <QualityQueryProvider>
      <MaintenanceRecordsPage />
    </QualityQueryProvider>
  )
}