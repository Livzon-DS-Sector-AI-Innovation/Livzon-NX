import { fetchNewEmployeesServer } from '@/lib/api/server/hr'
import EmployeeProfileClient from '@/components/hr/EmployeeProfileClient'

export default async function NewEmployeeProfilePage() {
  let res
  try {
    res = await fetchNewEmployeesServer({ page: 1, page_size: 20 })
  } catch {
    // 后端不可用时使用空数据初始化，客户端会自动重试
    res = { data: [], meta: { total: 0 } }
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)]">
          新厂员工档案
        </h1>
      </div>
      <EmployeeProfileClient
        initialEmployees={res.data}
        initialTotal={res.meta?.total || 0}
      />
    </div>
  )
}
