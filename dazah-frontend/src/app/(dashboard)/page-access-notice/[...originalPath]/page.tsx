import { headers } from 'next/headers'
import { notFound } from 'next/navigation'
import { PageAccessNotice } from '@/components/layout/PageAccessNotice'
import { MENU_PAGE_UNAVAILABLE, PAGE_ACCESS_NOTICE_HEADER, QUERY_PERMISSION_REQUIRED } from '@/lib/page-access-notice'

export default async function PageAccessNoticePage() {
  const reason = (await headers()).get(PAGE_ACCESS_NOTICE_HEADER)
  // Unmatched module URLs fall through to the shared Dashboard 404 boundary.
  if (reason !== QUERY_PERMISSION_REQUIRED && reason !== MENU_PAGE_UNAVAILABLE) notFound()
  return <PageAccessNotice reason={reason} />
}
