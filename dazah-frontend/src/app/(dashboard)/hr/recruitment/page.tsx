import { fetchJobPostingsServer } from '@/actions/hr'
import { HrQueryProvider } from '@/components/hr'
import RecruitmentClient from '@/components/hr/RecruitmentClient'

export const dynamic = 'force-dynamic'

export default async function RecruitmentPage() {
  let initialJobs: any[] = []

  try {
    const jobsRes = await fetchJobPostingsServer({ page: 1, page_size: 100 })
    initialJobs = jobsRes.data || []
  } catch {
    // 后端不可用时使用空数据初始化，客户端会自动重试
  }

  return (
    <HrQueryProvider>
      <RecruitmentClient
        initialJobs={initialJobs}
      />
    </HrQueryProvider>
  )
}
