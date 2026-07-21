import { fetchLabelVerificationsServer } from '@/actions/quality'
import LabelVerificationClient from '@/components/production/LabelVerificationClient'
import { redirect } from 'next/navigation'

export const dynamic = 'force-dynamic'

export default async function LabelVerificationPage() {
  let res = null
  let initialError: string | undefined
  try {
    res = await fetchLabelVerificationsServer({ page: 1, page_size: 20 })
  } catch (error) {
    const message = error instanceof Error ? error.message : '标签复核数据加载失败'
    if (/login required|未登录|unauthorized/i.test(message)) {
      redirect('/login?next=/production/label-verification')
    }
    initialError = message
  }

  return (
    <LabelVerificationClient
      initialVerifications={res?.data || []}
      initialTotal={res?.meta?.total || 0}
      initialError={initialError}
    />
  )
}
