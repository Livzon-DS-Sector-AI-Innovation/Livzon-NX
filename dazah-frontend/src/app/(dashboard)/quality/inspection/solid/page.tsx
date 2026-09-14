import { QualityQueryProvider } from '@/components/quality'
import { InspectionMaterialPage } from '@/components/quality/inspection'

export const dynamic = 'force-dynamic'

export default function InspectionSolidPage() {
  return (
    <QualityQueryProvider>
      <InspectionMaterialPage module="solid" />
    </QualityQueryProvider>
  )
}
