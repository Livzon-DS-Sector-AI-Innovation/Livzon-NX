import { fetchSupplementaryRepliesServer } from '@/actions/registration'
import SupplementaryReplyClient from '@/components/registration/SupplementaryReplyClient'

export const dynamic = 'force-dynamic'

export default async function SupplementaryReplyPage() {
  const repliesRes = await fetchSupplementaryRepliesServer({ page: 1, page_size: 20 })

  return (
    <SupplementaryReplyClient
      initialReplies={repliesRes?.data || []}
      initialTotal={repliesRes?.meta?.total || 0}
    />
  )
}
