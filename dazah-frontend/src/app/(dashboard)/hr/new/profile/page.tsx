import { fetchNewEmployeesServer } from '@/lib/api/server/hr'
import EmployeeProfileClient from '@/components/hr/EmployeeProfileClient'

export default async function NewEmployeeProfilePage() {
  const res = await fetchNewEmployeesServer({ page: 1, page_size: 20 })

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
