import { SafetyPageFeishuMirror } from '@/components/safety'
import { SAFETY_PAGE_TABLE_KEYS } from '@/lib/safety-page-tables'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: '危险化学品卸车巡查表 - DAZAH',
}

export const dynamic = 'force-dynamic'

export default function HazchemUnloadingInspectionPage() {
  return (
    <div className="p-6">
      <SafetyPageFeishuMirror
        pageKey={SAFETY_PAGE_TABLE_KEYS.hazchemUnloadingInspection}
        pageName="危险化学品卸车巡查表"
      />
    </div>
  )
}
