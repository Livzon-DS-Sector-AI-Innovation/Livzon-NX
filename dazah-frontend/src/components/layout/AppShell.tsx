"use client"

import { Suspense, useEffect, useState } from "react"
import { Button, Drawer } from 'antd'
import { MenuOutlined } from '@ant-design/icons'
import Link from "next/link"
import { usePathname } from "next/navigation"
import { AgentFloatingEntry } from "@/components/agent/AgentFloatingEntry"
import { MappedMenuPageGate } from "@/components/feishu-data"
import {
  expandEquipmentPagePermissions,
  getAuthorizedPageMenus,
  getModuleByKey,
  getPageKeyByPath,
  moduleMenus,
} from "@/lib/menu-config"
import { hasAnyEquipmentModuleAccess } from "@/lib/equipment-page-permissions"
import { TopNav } from "./TopNav"
import { Sidebar } from "./Sidebar"
import { PageNavigation } from "./PageNavigation"
import type { User } from "@/types/user"
import { useAuthStore } from "@/stores/auth"

interface AppShellProps {
  children: React.ReactNode
  user: User
}

export function AppShell({ children, user }: AppShellProps) {
  const setUser = useAuthStore((state) => state.setUser)

  useEffect(() => {
    setUser({
      id: user.id,
      name: user.name,
      role: user.role,
      roles: user.roles,
      permissions: user.permissions,
      page_permissions: user.page_permissions,
      page_permission_rollouts: user.page_permission_rollouts,
      grant_version: user.grant_version,
    })
  }, [setUser, user])

  const pathname = usePathname()
  const [mobileSidebarPath, setMobileSidebarPath] = useState<string | null>(null)
  const moduleKey = pathname.split("/")[1]
  const currentModule = getModuleByKey(moduleKey)
  // 系统管理员不依赖逐项授权；普通用户缺失授权仍保持默认拒绝。
  const authorizedModules = user.role === 'admin'
    ? moduleMenus
    : getAuthorizedPageMenus(
        user.module_codes,
        user.page_permissions,
      )
  const isModuleDenied = Boolean(
    currentModule &&
      user.role !== 'admin' &&
      !authorizedModules.some(
        (module) => module.moduleCode === currentModule.moduleCode,
      ),
  )
  const currentPageKey = getPageKeyByPath(pathname)
  const nativeEnergyPage = currentModule?.moduleCode === 'energy' && new Set([
    'energy:ledger-overview', 'energy:entry', 'energy:reports',
    'energy:analysis', 'energy:data-quality', 'energy:settings',
  ]).has(currentPageKey ?? '')
  // 展开旧「车间×功能」叶授权后查找；设备统一工作台按任一功能模块授权放行
  const pageGrant = expandEquipmentPagePermissions(user.page_permissions).find(
    (grant) => grant.page_key === currentPageKey,
  )
  const consoleAccess = currentPageKey === 'equipment:console'
    && hasAnyEquipmentModuleAccess(user)
  const isPageDenied = Boolean(
    user.role !== 'admin' &&
      !consoleAccess &&
      (!currentPageKey || !pageGrant?.permissions?.includes("access")),
  )
  const isQueryDenied = Boolean(
    user.role !== 'admin' &&
      pageGrant?.permissions?.includes("access") &&
      !pageGrant.permissions.includes("query"),
  )

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <TopNav user={user} modules={authorizedModules} />
      <div className="flex flex-1 overflow-hidden">
        <div className={`${nativeEnergyPage ? 'hidden min-[701px]:flex' : 'flex'} shrink-0`}>
        <Suspense
          fallback={
            <aside className="w-56 shrink-0 border-r border-[var(--color-hairline)] bg-[var(--color-canvas)]" />
          }
        >
          <Sidebar user={user} modules={authorizedModules} />
        </Suspense>
        </div>
        <main className={`flex-1 min-w-0 overflow-y-auto bg-[var(--color-surface)] ${nativeEnergyPage ? 'p-3 min-[701px]:p-6' : 'p-6'}`}>
          {nativeEnergyPage && <div className="mb-3 min-[701px]:hidden"><Button aria-label="能源菜单" icon={<MenuOutlined />} onClick={() => setMobileSidebarPath(pathname)}>能源菜单</Button><Drawer title="能源菜单" placement="left" size={280} open={mobileSidebarPath === pathname} onClose={() => setMobileSidebarPath(null)} destroyOnHidden><Suspense fallback={null}><Sidebar user={user} modules={authorizedModules} /></Suspense></Drawer></div>}
          {isModuleDenied ? (
            <section className="mx-auto flex min-h-full max-w-xl items-center justify-center">
              <div className="w-full rounded-[var(--rounded-lg)] border border-[var(--color-hairline)] bg-[var(--color-canvas)] p-8 text-center">
                <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)]">
                  暂无模块访问权限
                </h1>
                <p className="mt-3 text-[14px] leading-6 text-[var(--color-steel)]">
                  当前账号在“{currentModule?.label}”中没有可访问页面，请联系管理员调整角色或页面授权。
                </p>
              </div>
            </section>
          ) : isPageDenied ? (
            <section className="mx-auto flex min-h-full max-w-xl items-center justify-center">
              <div className="w-full rounded-[var(--rounded-lg)] border border-[var(--color-hairline)] bg-[var(--color-canvas)] p-8 text-center">
                <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)]">
                  暂无页面访问权限
                </h1>
                <p className="mt-3 text-[14px] leading-6 text-[var(--color-steel)]">
                  当前账号未获得此菜单页面的访问权限，请联系管理员调整页面授权。
                </p>
                {user.role === "admin" && (
                  <Link
                    href="/settings"
                    className="mt-5 inline-flex rounded-[var(--rounded-sm)] bg-[var(--color-primary)] px-4 py-2 text-[14px] font-medium text-white transition-colors hover:bg-[var(--color-primary-pressed)]"
                  >
                    前往系统设置
                  </Link>
                )}
              </div>
            </section>
          ) : isQueryDenied ? (
            <section className="mx-auto flex min-h-full max-w-xl items-center justify-center">
              <div className="w-full rounded-[var(--rounded-lg)] border border-[var(--color-hairline)] bg-[var(--color-canvas)] p-8 text-center">
                <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)]">
                  当前页面仅允许访问
                </h1>
                <p className="mt-3 text-[14px] leading-6 text-[var(--color-steel)]">
                  当前账号没有查询权限，因此页面不会发起业务数据请求。
                </p>
              </div>
            </section>
          ) : (
            <>
              <Suspense fallback={null}>
                <PageNavigation modules={authorizedModules} />
              </Suspense>
              <MappedMenuPageGate moduleCode={currentModule?.moduleCode}>
                {children}
              </MappedMenuPageGate>
            </>
          )}
        </main>
      </div>
      <AgentFloatingEntry />
    </div>
  )
}
