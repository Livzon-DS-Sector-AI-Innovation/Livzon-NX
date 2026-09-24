import { fetchEmployees } from '@/actions/hr'
import EmployeeProfileClient from '@/components/hr/EmployeeProfileClient'
import type { Employee } from '@/types/hr'

export const dynamic = 'force-dynamic'

interface PageProps {
  searchParams: Promise<{ department?: string }>
}

export default async function EmployeeProfilePage({ searchParams }: PageProps) {
  const { department } = (await searchParams) || {}
  let initialEmployees: Employee[] = []
  let initialTotal = 0

  try {
    const res = await fetchEmployees({ page: 1, page_size: 20 })
    initialEmployees = res.data || []
    initialTotal = res.meta?.total || 0
  } catch {
    // 后端不可用时使用空数据初始化，客户端会自动重试
  }

  return (
    <EmployeeProfileClient
      initialEmployees={initialEmployees}
      initialTotal={initialTotal}
      initialDepartment={department || ''}
    />
  )
}
