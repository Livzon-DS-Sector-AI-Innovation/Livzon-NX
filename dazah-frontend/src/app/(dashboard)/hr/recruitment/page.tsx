import { fetchJobPostingsServer } from '@/actions/hr'
import { HrQueryProvider } from '@/components/hr'
import RecruitmentClient from '@/components/hr/RecruitmentClient'

export const dynamic = 'force-dynamic'

export default async function RecruitmentPage() {
  const jobsRes = await fetchJobPostingsServer({ page: 1, page_size: 100 })

  return (
    <HrQueryProvider>
      <RecruitmentClient
        initialJobs={jobsRes.data || []}
      />
    </HrQueryProvider>
  )
}
