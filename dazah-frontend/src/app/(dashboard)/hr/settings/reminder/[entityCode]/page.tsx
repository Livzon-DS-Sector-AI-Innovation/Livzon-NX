import { ReminderDetailClient } from '@/components/hr'

export const dynamic = 'force-dynamic'

export default function ReminderDetailPage({
  params,
}: {
  params: Promise<{ entityCode: string }>
}) {
  return <ReminderDetailClient params={params} />
}
