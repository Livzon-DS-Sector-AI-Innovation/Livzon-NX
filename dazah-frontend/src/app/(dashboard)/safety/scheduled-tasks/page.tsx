import { getScheduledTasks } from '@/actions/safety'
import { ScheduledTaskList } from '@/components/safety'
import { readListPagination, type ServerQueryRecord } from '@/lib/list-url-state'

export const dynamic = 'force-dynamic'

export default async function ScheduledTasksPage({ searchParams }: {
  searchParams: Promise<ServerQueryRecord>
}) {
  const query = await searchParams
  const { page, pageSize } = readListPagination(query)
  const res = await getScheduledTasks({ page, page_size: pageSize })

  return (
    <div style={{ padding: '0 0 24px' }}>
      <h2 style={{ marginBottom: 16 }}>定时任务</h2>
      <ScheduledTaskList
        key={`${page}:${pageSize}`}
        initialData={res.data || []}
        initialTotal={res.meta?.total || 0}
      />
    </div>
  )
}
