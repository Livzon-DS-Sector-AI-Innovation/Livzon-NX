"use client"

import { Suspense, useEffect } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { AgentFloatingEntry } from "@/components/agent/AgentFloatingEntry"
import { MappedMenuPageGate } from "@/components/feishu-data"
import {
  getAuthorizedPageMenus,
  getModuleByKey,
  getPageKeyByPath,
  moduleMenus,
} from "@/lib/menu-config"
import { TopNav } from "./TopNav"
import { Sidebar } from "./Sidebar"
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
  const moduleKey = pathname.split("/")[1]
  const currentModule = getModuleByKey(moduleKey)
  // 系统管理员不依赖逐项授权；普通用户缺失授权仍保持默认拒绝。
  const authorizedModules = user.role === 'admin'
    ? moduleMenus
    : getAuthorizedPageMenus(
        user.module_codes,
        user.page_permissions,
        user.page_permission_rollouts,
      )
  const isModuleDenied = Boolean(
    currentModule &&
      !authorizedModules.some(
        (module) => module.moduleCode === currentModule.moduleCode,
      ),
  )
  const currentPageKey = getPageKeyByPath(pathname)
  const pageGrant = user.page_permissions?.find(
    (grant) => grant.page_key === currentPageKey,
  )
  const isPagePolicyEnforced = Boolean(
    user.role !== 'admin' && currentModule && user.page_permission_rollouts?.[currentModule.moduleCode] === "enforced",
  )
  const isPageDenied = Boolean(
    isPagePolicyEnforced &&
      (!currentPageKey || !pageGrant?.permissions?.includes("access")),
  )
  const isQueryDenied = Boolean(
    isPagePolicyEnforced &&
      pageGrant?.permissions?.includes("access") &&
      !pageGrant.permissions.includes("query"),
  )

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <TopNav user={user} modules={authorizedModules} />
      <div className="flex flex-1 overflow-hidden">
        <Suspense
          fallback={
            <aside className="w-56 shrink-0 border-r border-[var(--color-hairline)] bg-[var(--color-canvas)]" />
          }
        >
          <Sidebar user={user} modules={authorizedModules} />
        </Suspense>
        <main className="flex-1 overflow-y-auto bg-[var(--color-surface)] p-6">
          {isModuleDenied || isPageDenied ? (
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
            <MappedMenuPageGate moduleCode={currentModule?.moduleCode}>
              {children}
            </MappedMenuPageGate>
          )}
        </main>
      </div>
      <AgentFloatingEntry />
    </div>
  )
}
