"use client"

import Link from "next/link"
import { usePathname, useSearchParams } from "next/navigation"
import { useEffect, useState } from "react"
import { Avatar } from "antd"
import { LoadingOutlined, UserOutlined } from "@ant-design/icons"
import type { ModuleMenu } from "@/lib/menu-config"
import { ModuleIcon, SearchIcon, BellIcon } from "@/components/icons"
import type { User } from "@/types/user"

interface TopNavProps {
  user: User
  modules: ModuleMenu[]
}

export function TopNav({ user, modules }: TopNavProps) {
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const activeModule = pathname.split("/")[1] || "production"
  const displayName = user.name || user.username || "用户"
  const authToken = searchParams.get("auth_token")
  const currentHref = `${pathname}?${searchParams.toString()}`
  const [pendingNavigation, setPendingNavigation] = useState<{
    fromHref: string
    moduleKey: string
  } | null>(null)
  const pendingModule = pendingNavigation?.fromHref === currentHref &&
    pendingNavigation.moduleKey !== activeModule
    ? pendingNavigation.moduleKey
    : null

  useEffect(() => {
    if (!pendingNavigation) return
    const timeout = window.setTimeout(() => setPendingNavigation(null), 15_000)
    return () => window.clearTimeout(timeout)
  }, [pendingNavigation])

  const withAuthToken = (path: string) => {
    if (!authToken) return path
    const [targetPath, queryString = ""] = path.split("?")
    const params = new URLSearchParams(queryString)
    if (!params.has("auth_token")) {
      params.set("auth_token", authToken)
    }
    const nextQuery = params.toString()
    return `${targetPath}${nextQuery ? `?${nextQuery}` : ""}`
  }

  return (
    <header className="h-16 bg-[var(--color-canvas)] border-b border-[var(--color-hairline)] flex items-center px-5 shrink-0">
      {/* Logo */}
      <div className="flex items-center gap-2.5 mr-4 shrink-0">
        <div className="w-7 h-7 rounded-[var(--rounded-md)] bg-[var(--color-primary)] flex items-center justify-center">
          <span className="text-white text-xs font-semibold">API</span>
        </div>
        <div className="flex flex-col">
          <span className="text-[var(--color-charcoal)] text-[15px] font-semibold tracking-tight leading-tight">
            原料药
          </span>
          <span className="text-[var(--color-steel)] text-[11px] leading-tight">
            丽珠集团（宁夏）制药有限公司
          </span>
        </div>
      </div>

      {/* Module Tabs */}
      <nav aria-label="业务模块" className="flex items-center gap-1.5 flex-1 overflow-x-auto scrollbar-hide h-full ml-2">
        {modules.map((mod) => {
          const isActive = activeModule === mod.key
          const isPending = pendingModule === mod.key
          return (
            <Link
              key={mod.key}
              href={withAuthToken(mod.path)}
              className="top-nav-tab"
              aria-current={isActive ? "location" : undefined}
              data-pending={isPending || undefined}
              onClick={(event) => {
                if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
                if (!isActive) setPendingNavigation({ fromHref: currentHref, moduleKey: mod.key })
              }}
            >
              {isPending
                ? <LoadingOutlined spin aria-hidden className="text-[16px]" />
                : <ModuleIcon name={mod.icon} className="w-4 h-4" />}
              {mod.label}
            </Link>
          )
        })}
      </nav>

      {/* Right Section */}
      <div className="flex items-center gap-1.5 ml-4 shrink-0">
        <button type="button" aria-label="搜索" className="top-nav-action">
          <SearchIcon className="w-[18px] h-[18px]" />
        </button>
        <button type="button" aria-label="通知" className="top-nav-action relative">
          <BellIcon className="w-[18px] h-[18px]" />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-[var(--color-error)] rounded-full" />
        </button>
        <div className="ml-2 flex items-center gap-2 h-8 px-2 rounded-[var(--rounded-md)]">
          <Avatar
            size={28}
            src={user.avatar_url || undefined}
            icon={<UserOutlined />}
          />
          <span className="text-[13px] text-[var(--color-ink)] hidden md:inline">
            {displayName}
          </span>
          <Link
            href="/auth/logout"
            prefetch={false}
            className="top-nav-exit hidden md:inline-flex"
          >
            退出
          </Link>
        </div>
      </div>
    </header>
  )
}
