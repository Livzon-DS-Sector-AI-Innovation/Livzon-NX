import { SafetyPageFeishuMirror } from '@/components/safety'
import {
  SAFETY_PAGE_TABLE_CREATE_URLS,
  SAFETY_PAGE_TABLE_KEYS,
  SAFETY_PAGE_TABLE_PREFERRED_COLUMNS,
} from '@/lib/safety-page-tables'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'EHS变更审批 - DAZAH',
}

export const dynamic = 'force-dynamic'

export default function EhsChangeReviewPage() {
  return (
    <div className="p-6">
      <SafetyPageFeishuMirror
        pageKey={SAFETY_PAGE_TABLE_KEYS.ehsChangeReview}
        pageName="EHS变更审批"
        preferredColumnNames={
          SAFETY_PAGE_TABLE_PREFERRED_COLUMNS[
            SAFETY_PAGE_TABLE_KEYS.ehsChangeReview
          ]
        }
        createUrl={SAFETY_PAGE_TABLE_CREATE_URLS[SAFETY_PAGE_TABLE_KEYS.ehsChangeReview]}
      />
    </div>
  )
}
