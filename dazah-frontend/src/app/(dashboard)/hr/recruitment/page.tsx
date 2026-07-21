import { fetchCandidates } from '@/actions/hr'
import RecruitmentClient from '@/components/hr/RecruitmentClient'

export const dynamic = 'force-dynamic'

export default async function RecruitmentPage() {
  const res = await fetchCandidates({ page: 1, page_size: 20 })

  return (
    <RecruitmentClient
      initialCandidates={res.data}
      initialTotal={res.meta?.total || 0}
    />
  )
}
