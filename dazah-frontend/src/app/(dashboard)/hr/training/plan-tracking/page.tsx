import { Suspense } from 'react'
import { Spin } from 'antd'
import { PlanTrackingClient } from '@/components/hr'

export const dynamic = 'force-dynamic'

export default function PlanTrackingPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)] mb-2">
          培训计划跟踪
        </h1>
        <p className="text-[14px] text-[var(--color-steel)]">
          按年按月跟踪公司级/部门级年度培训计划执行情况（APP11-SMP-HR-002-14）
        </p>
      </div>

      <Suspense fallback={<Spin size="large" className="flex justify-center py-12" />}>
        <PlanTrackingClient />
      </Suspense>
    </div>
  )
}
