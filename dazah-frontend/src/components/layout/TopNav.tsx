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

interface FrequentPage {
  path: string
  count: number
}

const MAX_FREQUENT_PAGES = 5
const MAX_TRACKED_PAGES = 50

function readFrequentPages(userId: string): FrequentPage[] | null {
  try {
    const saved: unknown = JSON.parse(window.localStorage.getItem(`dazah-frequent-page-searches:${userId}`) || "[]")
    if (!Array.isArray(saved)) return []
    const entries: unknown[] = saved
    return entries.flatMap((entry) => {
      if (!entry || typeof entry !== "object" || !("path" in entry) || !("count" in entry)) return []
      const { path, count } = entry
      return typeof path === "string" && path.startsWith("/") &&
        typeof count === "number" && Number.isSafeInteger(count) && count > 0
        ? [{ path, count }]
        : []
    }).slice(0, MAX_TRACKED_PAGES)
  } catch {
    return null
  }
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
  const currentHref = `${pathname}?${searchParams.toString()}`
  const [pendingNavigation, setPendingNavigation] = useState<{
    fromHref: string
    moduleKey: string
  } | null>(null)
  const [resultsOpen, setResultsOpen] = useState(false)
  const [searchText, setSearchText] = useState("")
  const [frequentPages, setFrequentPages] = useState<{ userId: string; entries: FrequentPage[] }>({ userId: "", entries: [] })
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
  const currentFrequentPages = frequentPages.userId === user.id ? frequentPages.entries : []
  const availablePages = new Map(searchPages.map((page) => [page.path, page]))
  const frequentResults = [...currentFrequentPages]
    .sort((a, b) => b.count - a.count)
    .flatMap((entry) => availablePages.get(entry.path) || [])
    .slice(0, MAX_FREQUENT_PAGES)
  const openSearch = () => {
    const entries = readFrequentPages(user.id) ?? currentFrequentPages
    setFrequentPages({ userId: user.id, entries })
    setResultsOpen(true)
  }
  const recordSearch = (page: SearchPage) => {
    const previous = readFrequentPages(user.id) ?? currentFrequentPages
    const count = previous.find((entry) => entry.path === page.path)?.count || 0
    const entries = [{ path: page.path, count: Math.min(count + 1, Number.MAX_SAFE_INTEGER) },
      ...previous.filter((entry) => entry.path !== page.path)]
      .sort((a, b) => b.count - a.count)
      .slice(0, MAX_TRACKED_PAGES)
    setFrequentPages({ userId: user.id, entries })
    try {
      window.localStorage.setItem(`dazah-frequent-page-searches:${user.id}`, JSON.stringify(entries))
    } catch {
      // Browsers may disable storage; keep the suggestions for this session.
    }
  }
  const closeSearch = useCallback(() => {
    setResultsOpen(false)
    setSearchText("")
  }, [setResultsOpen, setSearchText])
  const renderSearchPage = (page: SearchPage) => (
    <li key={page.key}>
      <Link
        href={page.path}
        onClick={() => {
          recordSearch(page)
          closeSearch()
        }}
        className="block rounded-[var(--rounded-sm)] px-3 py-2 text-[var(--color-ink)] hover:bg-[var(--color-surface)] focus-visible:outline-2 focus-visible:outline-[var(--color-primary)]"
      >
        <span className="block font-medium">{page.label}</span>
        <span className="block text-xs text-[var(--color-steel)]">{page.breadcrumb}</span>
      </Link>
    </li>
  )
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
              href={mod.path}
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
              onFocus={openSearch}
              onClick={openSearch}
              onChange={(event) => {
                setSearchText(event.target.value)
                if (frequentPages.userId !== user.id) {
                  setFrequentPages({ userId: user.id, entries: readFrequentPages(user.id) ?? [] })
                }
                setResultsOpen(true)
              }}
              onPressEnter={() => {
                if (searchResults.length > 0) {
                  recordSearch(searchResults[0])
                  router.push(searchResults[0].path)
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
                frequentResults.length > 0 ? (
                  <>
                    <p className="px-3 py-1 text-xs text-[var(--color-steel)]">常搜索页面</p>
                    <ul className="space-y-1">
                      {frequentResults.map(renderSearchPage)}
                    </ul>
                  </>
                ) : <p className="py-4 text-center text-[var(--color-steel)]">输入关键词查找可访问的页面</p>
              ) : searchResults.length === 0 ? (
                <p className="py-4 text-center text-[var(--color-steel)]">没有匹配的页面</p>
              ) : (
                <ul className="space-y-1">
                  {searchResults.map(renderSearchPage)}
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
