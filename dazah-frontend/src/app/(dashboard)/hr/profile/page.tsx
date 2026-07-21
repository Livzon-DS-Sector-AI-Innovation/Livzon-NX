import { fetchEmployees } from '@/actions/hr'
import EmployeeProfileClient from '@/components/hr/EmployeeProfileClient'

export const dynamic = 'force-dynamic'

export default async function EmployeeProfilePage() {
  const res = await fetchEmployees({ page: 1, page_size: 20 })

  return (
    <EmployeeProfileClient
      initialEmployees={res.data}
      initialTotal={res.meta?.total || 0}
    />
  )
}
