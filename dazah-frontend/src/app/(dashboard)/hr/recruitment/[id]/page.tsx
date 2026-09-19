import { fetchCandidateById } from '@/actions/hr'
import CandidateDetailClient from '@/components/hr/CandidateDetailClient'

export const dynamic = 'force-dynamic'

interface CandidateDetailPageProps {
  params: Promise<{ id: string }>
}

export default async function CandidateDetailPage({ params }: CandidateDetailPageProps) {
  const { id } = await params
  let candidate: Awaited<ReturnType<typeof fetchCandidateById>>['data'] | null = null

  try {
    candidate = (await fetchCandidateById(id)).data
  } catch {
    // 后端不可用时降级为提示，保证页面可打开
  }

  if (!candidate) {
    return (
      <div className="p-6">
        <div className="rounded-lg border border-[var(--color-hairline)] bg-white p-6 text-[14px] text-[var(--color-steel)]">
          候选人信息暂不可用，请稍后刷新重试。
        </div>
      </div>
    )
  }

  return <CandidateDetailClient candidate={candidate} />
}
