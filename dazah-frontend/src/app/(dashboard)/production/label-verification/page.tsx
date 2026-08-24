import { fetchLabelVerificationsServer } from '@/actions/quality'
import LabelVerificationClient from '@/components/production/LabelVerificationClient'

export const dynamic = 'force-dynamic'

export default async function LabelVerificationPage() {
  const res = await fetchLabelVerificationsServer({ page: 1, page_size: 20 })

  return (
    <LabelVerificationClient
      initialVerifications={res?.data || []}
      initialTotal={res?.meta?.total || 0}
    />
  )
}
