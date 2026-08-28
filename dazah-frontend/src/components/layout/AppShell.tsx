"use client"

import { Suspense, useEffect } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { AgentFloatingEntry } from "@/components/agent/AgentFloatingEntry"
import { MappedMenuPageGate } from "@/components/feishu-data"
import {
  getAuthorizedModuleMenus,
  getModuleByKey,
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
      roles: user.roles,
      permissions: user.permissions,
    })
  }, [setUser, user])

  const pathname = usePathname()
  const moduleKey = pathname.split("/")[1]
  const currentModule = getModuleByKey(moduleKey)
  const authorizedModules = getAuthorizedModuleMenus(user.module_codes)
  const isModuleDenied = Boolean(
    currentModule &&
      !authorizedModules.some(
        (module) => module.moduleCode === currentModule.moduleCode,
      ),
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
          {isModuleDenied ? (
            <section className="mx-auto flex min-h-full max-w-xl items-center justify-center">
              <div className="w-full rounded-[var(--rounded-lg)] border border-[var(--color-hairline)] bg-[var(--color-canvas)] p-8 text-center">
                <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)]">
                  暂无模块访问权限
                </h1>
                <p className="mt-3 text-[14px] leading-6 text-[var(--color-steel)]">
                  当前账号未获“{currentModule?.label}”的查看权限，请联系管理员调整模块授权。
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
