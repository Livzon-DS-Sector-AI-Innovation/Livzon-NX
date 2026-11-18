import { notFound } from 'next/navigation'
import { Result } from 'antd'
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
  if (!taskRes.ok) return <Result status="error" title="无法加载审核任务" subTitle={taskRes.message} />
  if (!taskRes.data?.data) {
    notFound()
  }

  const [filesRes, issuesRes, reportRes] = await Promise.all([
    fetchFilesServer(id),
    fetchIssuesServer(id),
    fetchReportServer(id),
  ])
  if (!filesRes.ok) return <Result status="error" title="无法加载审核文件" subTitle={filesRes.message} />
  if (!issuesRes.ok) return <Result status="error" title="无法加载审核问题" subTitle={issuesRes.message} />
  if (!reportRes.ok) return <Result status="error" title="无法加载审核报告" subTitle={reportRes.message} />

  return (
    <ValidationAuditDetailClient
      task={taskRes.data.data}
      initialFiles={filesRes.data?.data ?? []}
      initialIssues={issuesRes.data?.data ?? []}
      initialReport={reportRes.data?.data ?? null}
    />
  )
}
