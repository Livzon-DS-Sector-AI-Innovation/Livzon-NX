import { QualityQueryProvider } from '@/components/quality'
import { InspectionMaterialPage } from '@/components/quality/inspection'

export const dynamic = 'force-dynamic'

export default function InspectionLiquidPage() {
  return (
    <QualityQueryProvider>
      <InspectionMaterialPage module="liquid" />
    </QualityQueryProvider>
  )
}
