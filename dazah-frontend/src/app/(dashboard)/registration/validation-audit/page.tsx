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
  const items = res?.data.items ?? []
  const total = res?.meta?.total ?? res?.data.total ?? 0

  return (
    <ValidationAuditListClient
      key={`${page}:${pageSize}`}
      initialTasks={items}
      initialTotal={total}
    />
  )
}
