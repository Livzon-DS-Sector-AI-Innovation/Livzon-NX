import { SupplierQualificationPage, QualityQueryProvider } from '@/components/quality'

export const dynamic = 'force-dynamic'

export default function SupplierQualificationRoute() {
  return (
    <QualityQueryProvider>
      <SupplierQualificationPage />
    </QualityQueryProvider>
  )
}
