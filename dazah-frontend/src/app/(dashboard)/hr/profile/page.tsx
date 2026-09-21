import { fetchEmployees } from '@/actions/hr'
import EmployeeProfileClient from '@/components/hr/EmployeeProfileClient'

export const dynamic = 'force-dynamic'

export default async function EmployeeProfilePage() {
  let initialEmployees: any[] = []
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
    />
  )
}
