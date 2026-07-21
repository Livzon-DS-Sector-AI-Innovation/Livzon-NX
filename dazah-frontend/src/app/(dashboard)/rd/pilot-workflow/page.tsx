import { PilotWorkflowList } from '@/components/rd/pilot-workflow/PilotWorkflowList'
import { fetchPilotWorkflows } from '@/actions/rd'
import { PilotWorkflowListResponse } from '@/types/pilot-workflow'

export const dynamic = 'force-dynamic'

export default async function PilotWorkflowListPage() {
  let initialData: PilotWorkflowListResponse = {
    items: [],
    total: 0,
    page: 1,
    page_size: 20,
  }

  try {
    initialData = await fetchPilotWorkflows({ page: 1, page_size: 20 })
  } catch (error) {
    console.warn('中试工作流加载失败:', error)
  }

  return <PilotWorkflowList initialData={initialData} />
}
