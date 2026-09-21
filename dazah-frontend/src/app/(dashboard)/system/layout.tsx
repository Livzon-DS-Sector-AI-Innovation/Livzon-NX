import { getCurrentUser } from '@/actions/auth'
import { isSystemAdministrator } from '@/lib/administrator-role'
import { notFound } from 'next/navigation'

export default async function SystemSettingsLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const user = await getCurrentUser()
  if (!user || !isSystemAdministrator(user)) notFound()
  return children
}
