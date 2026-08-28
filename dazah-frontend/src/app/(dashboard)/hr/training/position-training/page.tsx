import { Suspense } from 'react'
import { Spin } from 'antd'
import { PositionTrainingListClient } from '@/components/hr'

export const dynamic = 'force-dynamic'

export default function PositionTrainingPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)] mb-2">
          岗位培训清单
        </h1>
        <p className="text-[14px] text-[var(--color-steel)]">
          按部门和岗位管理培训教材清单（APP9-SMP-HR-002-14）
        </p>
      </div>

      <Suspense fallback={<Spin size="large" className="flex justify-center py-12" />}>
        <PositionTrainingListClient />
      </Suspense>
    </div>
  )
}
