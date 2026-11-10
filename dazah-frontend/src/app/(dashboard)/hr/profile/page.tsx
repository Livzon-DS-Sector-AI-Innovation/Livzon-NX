import { fetchEmployees } from '@/actions/hr'
import EmployeeProfileClient from '@/components/hr/EmployeeProfileClient'
import { employeeProfileQuery, readEmployeeProfileFilters } from '@/components/hr/employeeProfileQuery'
import { firstQueryValue, readListPagination, type ServerQueryRecord } from '@/lib/list-url-state'
import type { Employee } from '@/types/hr'

export const dynamic = 'force-dynamic'

interface PageProps {
  searchParams: Promise<ServerQueryRecord>
}

export default async function EmployeeProfilePage({ searchParams }: PageProps) {
  const query = (await searchParams) || {}
  const filters = readEmployeeProfileFilters(key => firstQueryValue(query[key]))
  const { page, pageSize } = readListPagination(query)
  let initialEmployees: Employee[] = []
  let initialTotal = 0

  try {
    const res = await fetchEmployees(employeeProfileQuery(filters, page, pageSize))
    initialEmployees = res.data || []
    initialTotal = res.meta?.total || 0
  } catch {
    // 后端不可用时使用空数据初始化，客户端会自动重试
  }

  return (
    <EmployeeProfileClient
      initialEmployees={initialEmployees}
      initialTotal={initialTotal}
    />
  )
}
