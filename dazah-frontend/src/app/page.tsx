import { redirect } from 'next/navigation'
import { getCurrentUser } from '@/actions/auth'
import { getFirstAuthorizedModulePath } from '@/lib/menu-config'

export const dynamic = 'force-dynamic'

export default async function RootPage() {
  const user = await getCurrentUser()
  redirect(user ? getFirstAuthorizedModulePath(user) : '/login')
}
