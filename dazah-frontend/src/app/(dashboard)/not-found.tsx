import { PageAccessNotice } from '@/components/layout/PageAccessNotice'
import { PAGE_NOT_FOUND } from '@/lib/page-access-notice'

export default function DashboardNotFound() {
  return <PageAccessNotice reason={PAGE_NOT_FOUND} />
}
