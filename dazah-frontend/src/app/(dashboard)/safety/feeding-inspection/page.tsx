import { SafetyPageFeishuMirror } from '@/components/safety'
import { SAFETY_PAGE_TABLE_KEYS } from '@/lib/safety-page-tables'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: '投料巡查表 - DAZAH',
}

export const dynamic = 'force-dynamic'

export default function FeedingInspectionPage() {
  return (
    <div className="p-6">
      <SafetyPageFeishuMirror
        pageKey={SAFETY_PAGE_TABLE_KEYS.feedingInspection}
        pageName="投料巡查表"
      />
    </div>
  )
}
