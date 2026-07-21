import { notFound } from 'next/navigation'
import {
  fetchTaskByIdServer,
  fetchFilesServer,
  fetchIssuesServer,
  fetchReportServer,
} from '@/actions/validation-audit'
import { ValidationAuditDetailClient } from '@/components/registration/validation-audit'

export const dynamic = 'force-dynamic'

export default async function ValidationAuditDetailPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  const taskRes = await fetchTaskByIdServer(id)
  if (!taskRes?.data) {
    notFound()
  }

  const [filesRes, issuesRes, reportRes] = await Promise.all([
    fetchFilesServer(id),
    fetchIssuesServer(id),
    fetchReportServer(id),
  ])

  return (
    <ValidationAuditDetailClient
      task={taskRes.data}
      initialFiles={filesRes?.data || []}
      initialIssues={issuesRes?.data || []}
      initialReport={reportRes?.data || null}
    />
  )
}
