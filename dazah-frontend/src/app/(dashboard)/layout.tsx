import { AntdProvider } from "@/components/AntdProvider"
import { AppShell } from "@/components/layout/AppShell"
import { getCurrentUser } from "@/actions/auth"
import { redirect } from "next/navigation"
import { headers } from "next/headers"
import { getModuleByKey, getPageKeyByPath } from "@/lib/menu-config"
import '@/lib/dayjs-config'

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

  const pathname = (await headers()).get('X-Dazah-Page-Path') || ''
  const moduleKey = pathname.split('/')[1]
  const currentModule = getModuleByKey(moduleKey)
  const pageKey = getPageKeyByPath(pathname)
  const pageGrant = user.page_permissions?.find(
    (grant) => grant.page_key === pageKey
  )
  const pagePolicyApplies = user.role !== 'admin' && Boolean(currentModule)
  const canAccess = !pagePolicyApplies || Boolean(pageGrant?.permissions?.includes('access'))
  const canQuery = !pagePolicyApplies || Boolean(pageGrant?.permissions?.includes('query'))
  const guardedChildren = canAccess && canQuery ? children : null

  return (
    <AntdProvider>
      <AppShell user={user}>{guardedChildren}</AppShell>
    </AntdProvider>
  )
}
