import { notFound, redirect } from 'next/navigation'
import { isRegistrationDeclarationProgressSheetKey } from '@/lib/registration-declaration-progress'

export const dynamic = 'force-dynamic'

interface DeclarationProgressSheetRouteProps {
  params: Promise<{ sheetKey: string }>
}

export default async function DeclarationProgressSheetRoute({
  params,
}: DeclarationProgressSheetRouteProps) {
  const { sheetKey } = await params

  if (!isRegistrationDeclarationProgressSheetKey(sheetKey)) {
    notFound()
  }
  redirect(`/registration/declaration-progress/${sheetKey}`)
}
