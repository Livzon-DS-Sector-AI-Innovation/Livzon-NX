import { AntdProvider } from "@/components/AntdProvider"
import { AppShell } from "@/components/layout/AppShell"
import { getCurrentUser } from "@/actions/auth"
import { redirect } from "next/navigation"
import { headers } from "next/headers"
import { expandEquipmentPagePermissions, getModuleByKey, getPageKeyByPath } from "@/lib/menu-config"
import { EQUIPMENT_CONSOLE_MODULE_HEADER, EQUIPMENT_MODULE_TABS, isEquipmentModule } from '@/lib/equipment-page-permissions'
import '@/lib/dayjs-config'
import MaintenanceBoundary from '@/components/shared/MaintenanceBoundary'

export const dynamic = 'force-dynamic'

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const user = await getCurrentUser()

  if (!user) {
    redirect('/login')
  }

  const requestHeaders = await headers()
  const pathname = requestHeaders.get('X-Dazah-Page-Path') || ''
  const moduleKey = pathname.split('/')[1]
  const currentModule = getModuleByKey(moduleKey)
  const equipmentConsole = pathname === '/equipment'
  const consoleModule = requestHeaders.get(EQUIPMENT_CONSOLE_MODULE_HEADER)
  const pageKeys = equipmentConsole
    ? EQUIPMENT_MODULE_TABS.filter((tab) => !isEquipmentModule(consoleModule) || tab.module === consoleModule).map((tab) => tab.key)
    : [getPageKeyByPath(pathname)]
  const grants = equipmentConsole ? expandEquipmentPagePermissions(user.page_permissions) : user.page_permissions
  const pagePolicyApplies = user.role !== 'admin' && Boolean(currentModule)
  const canRender = !pagePolicyApplies || pageKeys.some((pageKey) => {
    const grant = grants?.find((item) => item.page_key === pageKey)
    return grant?.permissions?.includes('access') && grant.permissions.includes('query')
  })

  return (
    <AntdProvider>
      <MaintenanceBoundary><AppShell user={user}>{canRender ? children : null}</AppShell></MaintenanceBoundary>
    </AntdProvider>
  )
}
