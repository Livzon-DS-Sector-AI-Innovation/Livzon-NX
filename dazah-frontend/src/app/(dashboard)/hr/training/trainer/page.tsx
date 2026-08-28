import { Suspense } from 'react'
import { Spin } from 'antd'
import { TrainerListClient } from '@/components/hr'

export const dynamic = 'force-dynamic'

export default function TrainerPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)] mb-2">
          培训师管理
        </h1>
        <p className="text-[14px] text-[var(--color-steel)]">
          管理企业内部培训师清单（APP8-SMP-HR-002-14）
        </p>
      </div>

      <Suspense fallback={<Spin size="large" className="flex justify-center py-12" />}>
        <TrainerListClient />
      </Suspense>
    </div>
  )
}
