import { SafetyPageFeishuMirror } from '@/components/safety'
import { SAFETY_PAGE_TABLE_KEYS } from '@/lib/safety-page-tables'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: '次日特殊危险作业审批 - DAZAH',
}

export const dynamic = 'force-dynamic'

export default function SpecialDangerWorkPage() {
  return (
    <div className="p-6">
      <SafetyPageFeishuMirror
        pageKey={SAFETY_PAGE_TABLE_KEYS.specialDangerWork}
        pageName="次日特殊危险作业审批"
      />
    </div>
  )
}
