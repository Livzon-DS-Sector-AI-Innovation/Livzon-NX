
import { Suspense } from 'react'
import { Spin } from 'antd'
import AnnualPlanListClient from '@/components/hr/AnnualPlanListClient'
import AnnualPlanDeptClient from '@/components/hr/AnnualPlanDeptClient'
import AnnualPlanDetailClient from '@/components/hr/AnnualPlanDetailClient'
import { fetchAnnualTrainingPlanByIdServer } from '@/lib/api/server/hr'

export const dynamic = 'force-dynamic'

interface PageProps {
  searchParams: Promise<{
    id?: string
    department?: string
  }>
}

export async function generateMetadata({ searchParams }: PageProps) {
  const params = await searchParams
  const planId = params.id
  const dept = params.department

  if (planId) {
    try {
      const res = await fetchAnnualTrainingPlanByIdServer(planId)
      if (res.data?.department) {
        return {
          title: `${res.data.department}${res.data.year}年度培训计划`,
        }
      }
    } catch {
      // fallback
    }
  }

  if (dept) {
    return { title: `${dept} - 年度培训计划` }
  }

  return { title: '年度培训计划' }
}

export default async function AnnualPlanPage({ searchParams }: PageProps) {
  const params = await searchParams
  const planId = params.id
  const dept = params.department

  // 模式3: 编辑详情页 — 不在 Server Component 中预取，避免认证问题
  if (planId) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)] mb-2">
            年度培训计划
          </h1>
          <p className="text-[14px] text-[var(--color-steel)]">
            编辑年度培训计划明细
          </p>
        </div>

        <Suspense
          fallback={
            <div className="flex items-center justify-center py-20">
              <Spin size="large" description="加载中..." />
            </div>
          }
        >
          <AnnualPlanDetailClient planId={planId} plan={null} />
        </Suspense>
      </div>
    )
  }

  // 模式2: 部门首页（展示该部门不同年份的计划）
  if (dept) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)] mb-2">
            年度培训计划
          </h1>
          <p className="text-[14px] text-[var(--color-steel)]">
            按部门管理年度培训计划，支持新建与编辑
          </p>
        </div>

        <Suspense
          fallback={
            <div className="flex items-center justify-center py-20">
              <Spin size="large" description="加载中..." />
            </div>
          }
        >
          <AnnualPlanDeptClient department={dept} />
        </Suspense>
      </div>
    )
  }

  // 模式1: 总列表页
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)] mb-2">
          年度培训计划
        </h1>
        <p className="text-[14px] text-[var(--color-steel)]">
          按部门管理年度培训计划，支持新建与编辑
        </p>
      </div>

      <Suspense
        fallback={
          <div className="flex items-center justify-center py-20">
            <Spin size="large" description="加载中..." />
          </div>
        }
      >
        <AnnualPlanListClient />
      </Suspense>
    </div>
  )
}
