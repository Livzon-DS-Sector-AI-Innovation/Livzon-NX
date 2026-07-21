import { fetchDepartments } from '@/actions/hr'
import { DepartmentClient } from '@/components/hr'

export const dynamic = 'force-dynamic'

export default async function DepartmentsPage() {
  const res = await fetchDepartments({ page: 1, page_size: 20 })

  return (
    <DepartmentClient
      initialDepartments={res.data}
      initialTotal={res.meta?.total || 0}
    />
  )
}
