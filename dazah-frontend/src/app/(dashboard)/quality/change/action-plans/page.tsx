import { Suspense } from 'react'
import { ChangeActionPlanPage } from '@/components/quality'

export default function QualityChangeActionPlanSubPage() {
  return (
    <Suspense fallback={null}>
      <ChangeActionPlanPage />
    </Suspense>
  )
}
