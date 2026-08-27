import { ChangeDashboardPage, QualityQueryProvider } from '@/components/quality'

export const dynamic = 'force-dynamic'

export default function QualityChangePage() {
  return (
    <QualityQueryProvider>
      <ChangeDashboardPage />
    </QualityQueryProvider>
  )
}
