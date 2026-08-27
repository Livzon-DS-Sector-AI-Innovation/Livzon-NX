export const dynamic = 'force-dynamic'

import TrainingLedgerPageClient from '@/components/hr/TrainingLedgerPageClient'

export default function TrainingLedgerPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)] mb-2">
          培训台账
        </h1>
        <p className="text-[14px] text-[var(--color-steel)]">
          年度培训统计表与 ESG 培训报表（SMP-HR-002-14）
        </p>
      </div>
      <TrainingLedgerPageClient />
    </div>
  )
}
