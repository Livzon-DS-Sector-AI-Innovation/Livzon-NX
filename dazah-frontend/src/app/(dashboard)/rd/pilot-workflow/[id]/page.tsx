import { PilotWorkflowDetail } from '@/components/rd/pilot-workflow/PilotWorkflowDetail'
import { fetchPilotWorkflow } from '@/actions/rd'

export const dynamic = 'force-dynamic'

export default async function PilotWorkflowDetailPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  let workflow = null

  try {
    workflow = await fetchPilotWorkflow(id)
  } catch (error) {
    console.warn('工作流详情加载失败:', error)
  }

  return <PilotWorkflowDetail workflowId={id} initialWorkflow={workflow} />
}
