import { Suspense } from 'react'
import { Spin } from 'antd'
import { EmployeeTrainingListClient } from '@/components/hr'

export const dynamic = 'force-dynamic'

export default function EmployeeTrainingListPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)] mb-2">
          员工培训清单
        </h1>
        <p className="text-[14px] text-[var(--color-steel)]">
          按人员汇总培训台账培训信息（HR-QD-01），支持配置人员、筛选与导出
        </p>
      </div>

      <Suspense fallback={<Spin size="large" className="flex justify-center py-12" />}>
        <EmployeeTrainingListClient />
      </Suspense>
    </div>
  )
}