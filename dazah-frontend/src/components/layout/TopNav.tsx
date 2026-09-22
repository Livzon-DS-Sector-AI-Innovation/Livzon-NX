"use client"

import Link from "next/link"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Avatar, Input } from "antd"
import { LoadingOutlined, UserOutlined } from "@ant-design/icons"
import { getPageKeyByPath, type ModuleMenu, type SubMenuItem } from "@/lib/menu-config"
import { ModuleIcon, SearchIcon } from "@/components/icons"
import type { User } from "@/types/user"

interface TopNavProps {
  user: User
  modules: ModuleMenu[]
}

interface SearchPage {
  key: string
  label: string
  breadcrumb: string
  path: string
}

function collectSearchPages(items: SubMenuItem[], ancestors: string[], isAdmin: boolean, queryablePages: Set<string>): SearchPage[] {
  return items.flatMap((item) => {
    if (item.disabled || (item.adminOnly && !isAdmin)) return []
    const labels = [...ancestors, item.label]
    const pageKey = item.path && getPageKeyByPath(item.path.split("?")[0])
    const page = item.path && (isAdmin || (pageKey && queryablePages.has(pageKey)))
      ? [{ key: `${labels.join("/")}:${item.path}`, label: item.label, breadcrumb: labels.join(" / "), path: item.path }]
      : []
    return [...page, ...collectSearchPages(item.children || [], labels, isAdmin, queryablePages)]
  })
}

export function TopNav({ user, modules }: TopNavProps) {
  const pathname = usePathname()
  const router = useRouter()
  const searchParams = useSearchParams()
  const activeModule = pathname.split("/")[1] || "production"
  const displayName = user.name || user.username || "用户"
  const authToken = searchParams.get("auth_token")
  const currentHref = `${pathname}?${searchParams.toString()}`
  const [pendingNavigation, setPendingNavigation] = useState<{
    fromHref: string
    moduleKey: string
  } | null>(null)
  const [resultsOpen, setResultsOpen] = useState(false)
  const [searchText, setSearchText] = useState("")
  const searchContainerRef = useRef<HTMLDivElement>(null)
  const searchPages = useMemo(() => {
    const queryablePages = new Set(user.page_permissions
      ?.filter((grant) => grant.permissions?.includes("query"))
      .map((grant) => grant.page_key))
    return modules.flatMap((module) => collectSearchPages(
      module.children, [module.label], user.role === "admin", queryablePages,
    ))
  }, [modules, user.page_permissions, user.role])
  const normalizedSearch = searchText.trim().toLocaleLowerCase()
  const searchResults = normalizedSearch
    ? searchPages.filter((page) => page.breadcrumb.toLocaleLowerCase().includes(normalizedSearch))
    : []
  const closeSearch = useCallback(() => {
    setResultsOpen(false)
    setSearchText("")
  }, [setResultsOpen, setSearchText])
  useEffect(() => {
    if (!resultsOpen) return
    const onPointerDown = (event: PointerEvent) => {
      if (event.target instanceof Node && !searchContainerRef.current?.contains(event.target)) closeSearch()
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        closeSearch()
      }
    }
    document.addEventListener("pointerdown", onPointerDown)
    document.addEventListener("keydown", onKeyDown)
    return () => {
      document.removeEventListener("pointerdown", onPointerDown)
      document.removeEventListener("keydown", onKeyDown)
    }
  }, [resultsOpen, closeSearch])
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
        <div ref={searchContainerRef} className="top-nav-search">
          <div className="top-nav-search-field">
            <Input
              aria-label="搜索页面名称"
              placeholder="输入页面或模块名称"
              value={searchText}
              onFocus={() => setResultsOpen(true)}
              onChange={(event) => {
                setSearchText(event.target.value)
                setResultsOpen(true)
              }}
              onPressEnter={() => {
                if (searchResults.length > 0) {
                  router.push(withAuthToken(searchResults[0].path))
                  closeSearch()
                }
              }}
            />
          </div>
          <span className="top-nav-search-icon" aria-hidden="true">
            <SearchIcon className="w-[18px] h-[18px]" />
          </span>
          {resultsOpen && (
            <div className="top-nav-search-results" role="region" aria-label="页面搜索结果" aria-live="polite">
              {!normalizedSearch ? (
                <p className="py-4 text-center text-[var(--color-steel)]">输入关键词查找可访问的页面</p>
              ) : searchResults.length === 0 ? (
                <p className="py-4 text-center text-[var(--color-steel)]">没有匹配的页面</p>
              ) : (
                <ul className="space-y-1">
                  {searchResults.map((page) => (
                    <li key={page.key}>
                      <Link
                        href={withAuthToken(page.path)}
                        onClick={closeSearch}
                        className="block rounded-[var(--rounded-sm)] px-3 py-2 text-[var(--color-ink)] hover:bg-[var(--color-surface)] focus-visible:outline-2 focus-visible:outline-[var(--color-primary)]"
                      >
                        <span className="block font-medium">{page.label}</span>
                        <span className="block text-xs text-[var(--color-steel)]">{page.breadcrumb}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
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
