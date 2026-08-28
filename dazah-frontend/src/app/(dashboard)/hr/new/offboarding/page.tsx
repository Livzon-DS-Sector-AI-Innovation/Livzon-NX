import { fetchNewOffboardingRecordsServer } from '@/lib/api/server/hr'
import { DepartureClient } from '@/components/hr'

export default async function NewOffboardingPage() {
  const res = await fetchNewOffboardingRecordsServer({ page: 1, page_size: 20 })

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)]">
          新厂离职管理
        </h1>
      </div>
      <DepartureClient
        initialRecords={res.data}
        initialTotal={res.meta?.total || 0}
      />
    </div>
  )
}
