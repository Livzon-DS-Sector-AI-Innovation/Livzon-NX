import { Suspense } from 'react'
import { Spin } from 'antd'
import { NewEmployeeTrainingDetailClient } from '@/components/hr'

export const dynamic = 'force-dynamic'

export default async function NewEmployeeTrainingDetailPage({
  params,
}: {
  params: Promise<{ planId: string }>
}) {
  const { planId } = await params
  return (
    <div className="space-y-6">
      <Suspense fallback={<Spin size="large" className="flex justify-center py-12" />}>
        <NewEmployeeTrainingDetailClient planId={planId} />
      </Suspense>
    </div>
  )
}