import { fetchFeishuDepartmentContactsAction } from '@/actions/quality'
import { DeviationInvestigationPushPage } from '@/components/quality'

export const dynamic = 'force-dynamic'

export default async function DeviationInvestigationsPage() {
  const contactResponse = await fetchFeishuDepartmentContactsAction(1, 1000).catch(() => ({
    items: [],
    total: 0,
    page: 1,
    page_size: 1000,
  }))

  return <DeviationInvestigationPushPage submitterContacts={contactResponse.items} />
}
