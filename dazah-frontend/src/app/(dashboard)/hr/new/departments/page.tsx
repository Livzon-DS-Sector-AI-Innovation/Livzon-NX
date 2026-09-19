import { fetchNewDepartmentsServer } from '@/lib/api/server/hr'
import { DepartmentClient } from '@/components/hr'

export default async function NewDepartmentsPage() {
  let res
  try {
    res = await fetchNewDepartmentsServer({ page: 1, page_size: 100 })
  } catch {
    // 后端不可用时使用空数据初始化，客户端会自动重试
    res = { data: [], meta: { total: 0 } }
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)]">
          新厂部门管理
        </h1>
      </div>
      <DepartmentClient
        initialDepartments={res.data}
        initialTotal={res.meta?.total || 0}
      />
    </div>
  )
}
