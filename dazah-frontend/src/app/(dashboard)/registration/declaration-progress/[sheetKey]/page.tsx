import { notFound } from 'next/navigation'

import { DeclarationProgressPage } from '@/components/registration'
import {
  ServerApiError,
  fetchDeclarationProgressSheetDetailServer,
} from '@/lib/api/server/registration'
import { isRegistrationDeclarationProgressSheetKey } from '@/lib/registration-declaration-progress'
import type { DeclarationProgressSheetDetail } from '@/types/registration'

export const dynamic = 'force-dynamic'

interface DeclarationProgressSheetPageProps {
  params: Promise<{ sheetKey: string }>
}

export default async function DeclarationProgressSheetRoute({
  params,
}: DeclarationProgressSheetPageProps) {
  const { sheetKey } = await params

  if (!isRegistrationDeclarationProgressSheetKey(sheetKey)) {
    notFound()
  }

  let detail: DeclarationProgressSheetDetail
  try {
    detail = await fetchDeclarationProgressSheetDetailServer(sheetKey)
  } catch (error) {
    if (error instanceof ServerApiError && error.status === 404) {
      // 子表不存在 → 404 页面，而非渲染崩溃
      notFound()
    }
    throw error
  }

  return <DeclarationProgressPage detail={detail} />
}
