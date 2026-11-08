import { getCertificateExpirySummary, getWorkCertificates } from '@/actions/safety'
import { WorkCertificatePanel } from '@/components/safety'

export const dynamic = 'force-dynamic'

export const metadata = {
  title: '特种作业证件 | 安全管理',
}

export default async function SafetyWorkCertificatesPage({
  searchParams,
}: {
  searchParams: Promise<{ cert?: string }>
}) {
  const { cert } = await searchParams
  const pageKey = 'safety:ops-safety:work-certificates'
  const [listRes, summaryRes] = await Promise.all([
    getWorkCertificates({ pageKey, page: 1, pageSize: 20 }),
    getCertificateExpirySummary(pageKey),
  ])
  const list = listRes.code === 200 && listRes.data ? listRes.data : null
  const summary =
    summaryRes.code === 200 && summaryRes.data ? summaryRes.data : null
  const initialError =
    listRes.code === 200 ? null : (listRes.message ?? '证件列表加载失败')

  return (
    <div style={{ padding: 24 }}>
      <WorkCertificatePanel
        initialList={list as never}
        initialSummary={summary}
        initialError={initialError}
        highlightCertId={cert ?? null}
      />
    </div>
  )
}
