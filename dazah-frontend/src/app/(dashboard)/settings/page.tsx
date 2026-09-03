import SettingsAdminClient from '@/components/settings/SettingsAdminClient'
import {
  serverFetchAdminUsers,
  serverFetchDepartments,
  serverFetchDeptRules,
  serverFetchMenus,
  serverFetchRoles,
} from '@/lib/api/server/admin'

export const dynamic = 'force-dynamic'

export default async function SettingsPage() {
  const [roles, departments, deptRules, menus, users] = await Promise.all([
    serverFetchRoles(),
    serverFetchDepartments(),
    serverFetchDeptRules(),
    serverFetchMenus(),
    serverFetchAdminUsers(),
  ])

  return (
    <SettingsAdminClient
      systemPermissions={{ roles, departments, deptRules, menus, users }}
    />
  )
}
