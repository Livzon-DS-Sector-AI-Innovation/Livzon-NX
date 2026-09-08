import { notFound } from 'next/navigation'

import { ProjectLedgerSheetPage } from '@/components/registration'
import { ServerApiError, fetchProjectLedgerSheetDetailServer } from '@/lib/api/server/registration'
import { isRegistrationProjectLedgerSheetKey } from '@/lib/registration-project-ledger'
import type { ProjectLedgerSheetDetail } from '@/types/registration'

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

  let detail: ProjectLedgerSheetDetail
  try {
    detail = await fetchProjectLedgerSheetDetailServer(sheetKey)
  } catch (error) {
    if (error instanceof ServerApiError && error.status === 404) {
      // 子表不存在 → 404 页面，而非渲染崩溃
      notFound()
    }
    throw error
  }

  return <ProjectLedgerSheetPage detail={detail} />
}
