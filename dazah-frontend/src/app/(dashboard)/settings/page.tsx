import SettingsAdminClient from '@/components/settings/SettingsAdminClient'
import { getCurrentUser } from '@/actions/auth'
import { isSystemAdministrator } from '@/lib/administrator-role'
import { notFound } from 'next/navigation'
import {
  serverFetchDepartments,
  serverFetchDeptRules,
  serverFetchRoles,
} from '@/lib/api/server/admin'

export const dynamic = 'force-dynamic'

export default async function SettingsPage({
  searchParams,
}: {
  searchParams: Promise<{ tab?: string | string[] }>
}) {
  const user = await getCurrentUser()
  if (!user || !isSystemAdministrator(user)) notFound()

  const requestedTab = (await searchParams).tab
  const activeTab = typeof requestedTab === 'string' ? requestedTab : 'users'
  const systemPermissions = activeTab === 'permissions'
    ? await Promise.all([
        serverFetchRoles(),
        serverFetchDepartments(),
        serverFetchDeptRules(),
      ]).then(([roles, departments, deptRules]) => ({ roles, departments, deptRules }))
    : null

  return (
    <SettingsAdminClient
      activeTab={activeTab}
      systemPermissions={systemPermissions}
    />
  )
}
