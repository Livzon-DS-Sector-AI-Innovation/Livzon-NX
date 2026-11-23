import { Result } from 'antd'
import { fetchTasksServer } from '@/actions/validation-audit'
import { ValidationAuditListClient } from '@/components/registration/validation-audit'
import { readListPagination, type ServerQueryRecord } from '@/lib/list-url-state'

export const dynamic = 'force-dynamic'

export default async function ValidationAuditPage({ searchParams }: {
  searchParams: Promise<ServerQueryRecord>
}) {
  const query = await searchParams
  const { page, pageSize } = readListPagination(query)
  const res = await fetchTasksServer({ page, page_size: pageSize })
  if (!res.ok) return <Result status="error" title="无法加载审核任务" subTitle={res.message} />
  const items = res.data?.data.items ?? []
  const total = res.data?.meta?.total ?? res.data?.data.total ?? 0

  return (
    <ValidationAuditListClient
      key={`${page}:${pageSize}`}
      initialTasks={items}
      initialTotal={total}
    />
  )
}
