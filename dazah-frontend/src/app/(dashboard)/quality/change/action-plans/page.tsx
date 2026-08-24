import { Suspense } from 'react'
import { ChangeActionPlanPage } from '@/components/quality'
import { QualityQueryProvider } from '@/components/quality'

export default function QualityChangeActionPlanSubPage() {
  return (
    <Suspense fallback={null}>
      <QualityQueryProvider>
        <ChangeActionPlanPage />
      </QualityQueryProvider>
    </Suspense>
  )
}
