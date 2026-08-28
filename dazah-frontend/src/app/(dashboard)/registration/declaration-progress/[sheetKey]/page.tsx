import { notFound } from 'next/navigation'

import { DeclarationProgressPage } from '@/components/registration'
import { fetchDeclarationProgressSheetDetailServer } from '@/lib/api/server/registration'
import { isRegistrationDeclarationProgressSheetKey } from '@/lib/registration-declaration-progress'

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

  const detail = await fetchDeclarationProgressSheetDetailServer(sheetKey)

  return <DeclarationProgressPage detail={detail} />
}
