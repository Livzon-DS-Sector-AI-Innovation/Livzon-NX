import { notFound } from 'next/navigation'

import { CertificateSheetPage } from '@/components/registration'
import { ServerApiError, fetchCertificateSheetDetailServer } from '@/lib/api/server/registration'
import { isRegistrationCertificateSheetKey } from '@/lib/registration-certificate'
import type { CertificateSheetDetail } from '@/types/registration'

export const dynamic = 'force-dynamic'

interface RegistrationCertificateSheetPageProps {
  params: Promise<{ sheetKey: string }>
}

export default async function RegistrationCertificateSheetPage({
  params,
}: RegistrationCertificateSheetPageProps) {
  const { sheetKey } = await params

  if (!isRegistrationCertificateSheetKey(sheetKey)) {
    notFound()
  }

  let detail: CertificateSheetDetail
  try {
    detail = await fetchCertificateSheetDetailServer(sheetKey)
  } catch (error) {
    if (error instanceof ServerApiError && error.status === 404) {
      // 子表不存在 → 404 页面，而非渲染崩溃
      notFound()
    }
    throw error
  }

  return <CertificateSheetPage detail={detail} />
}
