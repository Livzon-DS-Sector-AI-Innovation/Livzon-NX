import { fetchNewOnboardingRecordsServer } from '@/lib/api/server/hr'
import { OnboardingClient } from '@/components/hr'

export default async function NewOnboardingPage() {
  let res
  try {
    res = await fetchNewOnboardingRecordsServer({ page: 1, page_size: 20 })
  } catch {
    // 后端不可用时使用空数据初始化，客户端会自动重试
    res = { data: [], meta: { total: 0 } }
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)]">
          新厂入职台账
        </h1>
      </div>
      <OnboardingClient
        initialRecords={res.data}
        initialTotal={res.meta?.total || 0}
      />
    </div>
  )
}
