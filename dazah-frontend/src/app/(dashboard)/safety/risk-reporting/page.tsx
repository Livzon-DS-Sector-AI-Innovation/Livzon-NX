import { SafetyPageFeishuMirror } from '@/components/safety'
import { SAFETY_PAGE_TABLE_KEYS } from '@/lib/safety-page-tables'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: '关键风险作业报备 - DAZAH',
}

export const dynamic = 'force-dynamic'

export default function RiskReportingPage() {
  return (
    <div className="p-6">
      <SafetyPageFeishuMirror
        pageKey={SAFETY_PAGE_TABLE_KEYS.dailyRiskReport}
        pageName="关键风险作业报备"
      />
    </div>
  )
}
