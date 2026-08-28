import { SupplierDashboardPage, QualityQueryProvider } from '@/components/quality'

export const dynamic = 'force-dynamic'

export default function SupplierPage() {
  return (
    <QualityQueryProvider>
      <SupplierDashboardPage />
    </QualityQueryProvider>
  )
}
