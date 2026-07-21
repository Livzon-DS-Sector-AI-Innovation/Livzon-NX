import { fetchTasksServer } from '@/actions/validation-audit'
import { ValidationAuditListClient } from '@/components/registration/validation-audit'

export const dynamic = 'force-dynamic'

export default async function ValidationAuditPage() {
  const res = await fetchTasksServer({ page: 1, page_size: 20 })
  const items = res?.data?.items || res?.data || []
  const total = res?.meta?.total || res?.data?.total || 0

  return (
    <ValidationAuditListClient
      initialTasks={items}
      initialTotal={total}
    />
  )
}
