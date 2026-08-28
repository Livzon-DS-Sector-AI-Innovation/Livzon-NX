import { Suspense } from 'react'
import { Spin } from 'antd'
import { NewEmployeeTrainingListClient } from '@/components/hr'

export const dynamic = 'force-dynamic'

export default function NewEmployeeTrainingPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)] mb-2">
          新员工培训
        </h1>
        <p className="text-[14px] text-[var(--color-steel)]">
          新员工入职培训计划与进度跟踪（按岗位培训清单生成，培训执行走培训资料页面）
        </p>
      </div>

      <Suspense fallback={<Spin size="large" className="flex justify-center py-12" />}>
        <NewEmployeeTrainingListClient />
      </Suspense>
    </div>
  )
}