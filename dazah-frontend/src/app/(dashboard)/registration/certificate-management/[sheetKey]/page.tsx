import { notFound } from 'next/navigation'

import { CertificateSheetPage } from '@/components/registration'
import { fetchCertificateSheetDetailServer } from '@/lib/api/server/registration'
import { isRegistrationCertificateSheetKey } from '@/lib/registration-certificate'

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

  const detail = await fetchCertificateSheetDetailServer(sheetKey)

  return <CertificateSheetPage detail={detail} />
}
