import { notFound } from 'next/navigation'
import { getWorkPermitDetail } from '@/actions/safety'
import { WorkPermitDetailView } from '@/components/safety'

export const dynamic = 'force-dynamic'

export const metadata = {
  title: '作业票详情 | 安全管理',
}

export default async function WorkPermitDetailPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  const response = await getWorkPermitDetail(id, 'safety:ops-safety:work-permits')
  if (response.code !== 200 || !response.data) {
    notFound()
  }

  return (
    <div style={{ padding: 24 }}>
      <WorkPermitDetailView
        initialDetail={
          response.data as never
        }
      />
    </div>
  )
}
