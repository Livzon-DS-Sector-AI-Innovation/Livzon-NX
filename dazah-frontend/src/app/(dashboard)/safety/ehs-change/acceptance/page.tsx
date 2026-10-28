import { SafetyPageFeishuMirror } from '@/components/safety'
import {
  SAFETY_PAGE_TABLE_CREATE_URLS,
  SAFETY_PAGE_TABLE_KEYS,
  SAFETY_PAGE_TABLE_PREFERRED_COLUMNS,
} from '@/lib/safety-page-tables'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: '变更验收审批 - DAZAH',
}

export const dynamic = 'force-dynamic'

export default function EhsChangeAcceptancePage() {
  return (
    <div className="p-6">
      <SafetyPageFeishuMirror
        pageKey={SAFETY_PAGE_TABLE_KEYS.ehsChangeAcceptance}
        pageName="变更验收审批"
        preferredColumnNames={
          SAFETY_PAGE_TABLE_PREFERRED_COLUMNS[
            SAFETY_PAGE_TABLE_KEYS.ehsChangeAcceptance
          ]
        }
        createUrl={
          SAFETY_PAGE_TABLE_CREATE_URLS[SAFETY_PAGE_TABLE_KEYS.ehsChangeAcceptance]
        }
      />
    </div>
  )
}
