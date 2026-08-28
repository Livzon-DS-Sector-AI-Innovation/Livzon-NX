import { notFound } from 'next/navigation'

import { ProjectLedgerSheetPage } from '@/components/registration'
import { fetchProjectLedgerSheetDetailServer } from '@/lib/api/server/registration'
import { isRegistrationProjectLedgerSheetKey } from '@/lib/registration-project-ledger'

export const dynamic = 'force-dynamic'

interface ProjectLedgerSheetPageProps {
  params: Promise<{ sheetKey: string }>
}

export default async function ProjectLedgerSheetRoute({
  params,
}: ProjectLedgerSheetPageProps) {
  const { sheetKey } = await params

  if (!isRegistrationProjectLedgerSheetKey(sheetKey)) {
    notFound()
  }

  const detail = await fetchProjectLedgerSheetDetailServer(sheetKey)

  return <ProjectLedgerSheetPage detail={detail} />
}
