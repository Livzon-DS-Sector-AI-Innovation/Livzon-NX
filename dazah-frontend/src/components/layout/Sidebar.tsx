"use client"

import Link from "next/link"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { useEffect, useMemo, useState } from "react"
import { Menu } from "antd"
import type { MenuProps } from "antd"
import type { ModuleMenu, SubMenuItem } from "@/lib/menu-config"
import { LoadingOutlined, MenuFoldOutlined, MenuUnfoldOutlined, SettingOutlined } from "@ant-design/icons"
import type { User } from "@/types/user"
import { isSystemAdministrator } from "@/lib/administrator-role"

type MenuItem = Required<MenuProps>['items'][number]
const dashboardModules = new Set(['registration', 'quality', 'hr', 'warehouse'])

function parseMenuPath(path: string): { pathname: string; query: URLSearchParams } {
  const [pathname, queryString = ""] = path.split("?")
  return { pathname, query: new URLSearchParams(queryString) }
}

function queryContains(current: URLSearchParams, expected: URLSearchParams): boolean {
  for (const [key, value] of expected.entries()) {
    if (current.get(key) !== value) return false
  }
  return true
}

function matchesMenuPath(itemPath: string, pathname: string, query: URLSearchParams): boolean {
  const parsed = parseMenuPath(itemPath)
  if (parsed.query.size > 0) {
    return pathname === parsed.pathname && queryContains(query, parsed.query)
  }
  return pathname === parsed.pathname || pathname.startsWith(parsed.pathname + "/")
}

// ── 构建 key → path 映射（叶子节点 key 唯一，path 可重复）──
function buildKeyPathMap(items: SubMenuItem[]): Map<string, string> {
  const map = new Map<string, string>()
  for (const item of items) {
    if (item.children && item.children.length > 0) {
      const childMap = buildKeyPathMap(item.children)
      childMap.forEach((v, k) => map.set(k, v))
    }
    // 叶子与带 path 的父级（如仓储三个仪表盘入口）均可点击导航
    if (item.path) {
      map.set(item.key, item.path)
    }
  }
  return map
}

// ── 递归构建 Ant Design 菜单项 ──
function buildMenuItems(
  items: SubMenuItem[],
  moduleKey: string,
  prefetchPath?: (path: string) => void,
  onParentNavigate?: (path: string) => void,
  onParentTitleClick?: (key: string) => void,
  depth = 0,
): MenuItem[] {
  return items.map((item) => {
    if (item.children && item.children.length > 0) {
      const directDashboard = depth === 0 && item.dashboard && Boolean(item.path)
      const expandOnly = depth === 0 && dashboardModules.has(moduleKey) && !directDashboard
      const label =
        item.path && !item.disabled && !expandOnly ? (
          <span
            role="link"
            tabIndex={0}
            aria-label={`打开${item.label}${directDashboard ? '仪表盘' : '页面'}`}
            className="inline-flex w-full min-w-0 items-center rounded-[var(--rounded-sm)] focus-visible:outline-2 focus-visible:outline-[var(--color-primary)]"
            onClick={(event) => {
              event.stopPropagation()
              onParentNavigate?.(item.path)
            }}
            onKeyDown={(event) => {
              if (event.key !== 'Enter' && event.key !== ' ') return
              event.preventDefault()
              event.stopPropagation()
              onParentNavigate?.(item.path)
            }}
            onFocus={() => prefetchPath?.(item.path)}
            onMouseEnter={() => prefetchPath?.(item.path)}
          >
            <span className="min-w-0 truncate">{item.label}</span>
          </span>
        ) : (
          item.label
        )
      return {
        key: item.key,
        label,
        popupClassName: "sidebar-submenu-popup",
        onTitleClick: () => onParentTitleClick?.(item.key),
        children: buildMenuItems(item.children, moduleKey, prefetchPath, onParentNavigate, onParentTitleClick, depth + 1),
      }
    }
    const leaf: MenuItem = {
      key: item.key,
      label:
        item.path && !item.disabled ? (
          <span
            onFocus={() => prefetchPath?.(item.path)}
            onMouseEnter={() => prefetchPath?.(item.path)}
          >
            {item.label}
          </span>
        ) : (
          item.label
        ),
    }
    if (item.disabled) {
      leaf.disabled = true
    }
    return leaf
  })
}

// ── 收集所有可导航节点（叶子 + 带 path 的父级，跳过 disabled 和空 path）──
function collectNavigableItems(items: SubMenuItem[]): SubMenuItem[] {
  return items.flatMap((item) => {
    if (item.children && item.children.length > 0) {
      const parents = !item.disabled && item.path ? [item] : []
      return [...parents, ...collectNavigableItems(item.children)]
    }
    if (item.disabled || !item.path) return []
    return [item]
  })
}

// ── 查找当前路径匹配的可导航节点（叶子优先，父级落地页精确匹配）──
function findSelectedKey(
  items: SubMenuItem[],
  pathname: string,
  query: URLSearchParams,
): string | undefined {
  const navigable = collectNavigableItems(items)
  const sorted = navigable.sort((a, b) => {
    const aIsParent = Boolean(a.children && a.children.length > 0)
    const bIsParent = Boolean(b.children && b.children.length > 0)
    if (aIsParent !== bIsParent) return aIsParent ? 1 : -1
    return b.path.length - a.path.length
  })
  const match = sorted.find((item) => {
    if (item.children && item.children.length > 0) {
      // 父级落地页仅精确匹配，避免其前缀吞掉叶子高亮
      const parsed = item.path.split("?")
      return pathname === parsed[0]
    }
    return matchesMenuPath(item.path, pathname, query)
  })
  return match?.key
}

function splitMenuItemsByPlacement(items: SubMenuItem[]): {
  mainItems: SubMenuItem[]
  bottomItems: SubMenuItem[]
} {
  return items.reduce(
    (acc, item) => {
      if (item.placement === "bottom") {
        acc.bottomItems.push(item)
      } else {
        acc.mainItems.push(item)
      }
      return acc
    },
    { mainItems: [] as SubMenuItem[], bottomItems: [] as SubMenuItem[] },
  )
}

// ═══════════════════════════════════════════════════════════════

interface SidebarProps {
  user: User
  modules: ModuleMenu[]
}

export function filterMenuItemsByRole(items: SubMenuItem[], isAdmin: boolean): SubMenuItem[] {
  return items.flatMap((item) => {
    if (item.adminOnly && !isAdmin) return []
    if (!item.children || item.children.length === 0) return [item]

    const children = filterMenuItemsByRole(item.children, isAdmin)
    return children.length > 0 ? [{ ...item, children }] : []
  })
}

export function Sidebar({ user, modules }: SidebarProps) {
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const router = useRouter()
  const moduleKey = pathname.split("/")[1] || "production"
  const currentModule = modules.find((module) => module.key === moduleKey)
  const queryString = searchParams.toString()
  const query = useMemo(() => new URLSearchParams(queryString), [queryString])
  const currentHref = `${pathname}${queryString ? `?${queryString}` : ""}`
  const [pendingNavigation, setPendingNavigation] = useState<{
    fromHref: string
    targetHref: string
  } | null>(null)
  const [collapsed, setCollapsed] = useState(false)
  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      setCollapsed(window.localStorage.getItem(`dazah-sidebar-collapsed:${user.id}`) === "true")
    })
    return () => window.cancelAnimationFrame(frame)
  }, [user.id])
  const toggleCollapsed = () => {
    const nextCollapsed = !collapsed
    window.localStorage.setItem(`dazah-sidebar-collapsed:${user.id}`, String(nextCollapsed))
    setCollapsed(nextCollapsed)
    setOpenKeys([])
  }
  const pendingHref = pendingNavigation?.fromHref === currentHref
    ? pendingNavigation.targetHref
    : null
  const [menuOpenState, setMenuOpenState] = useState<{ href: string; keys: string[] }>({
    href: currentHref,
    keys: [],
  })
  const openKeys = menuOpenState.href === currentHref ? menuOpenState.keys : []
  const setOpenKeys = (nextKeys: string[] | ((keys: string[]) => string[])) => {
    setMenuOpenState((state) => {
      const keys = state.href === currentHref ? state.keys : []
      return {
        href: currentHref,
        keys: typeof nextKeys === "function" ? nextKeys(keys) : nextKeys,
      }
    })
  }

  useEffect(() => {
    if (!pendingNavigation) return
    if (pendingNavigation.fromHref !== currentHref) {
      const frame = window.requestAnimationFrame(() => setPendingNavigation(null))
      return () => window.cancelAnimationFrame(frame)
    }
    const timeout = window.setTimeout(() => setPendingNavigation(null), 60_000)
    return () => window.clearTimeout(timeout)
  }, [currentHref, pendingNavigation])

  const moduleChildren = useMemo(
    () => filterMenuItemsByRole(currentModule?.children || [], user.role === "admin"),
    [currentModule, user.role],
  )

  const { mainItems, bottomItems } = useMemo(
    () => splitMenuItemsByPlacement(moduleChildren),
    [moduleChildren],
  )
  const navigateTo = (path: string) => {
    if (path === currentHref) return
    setOpenKeys([])
    setPendingNavigation({ fromHref: currentHref, targetHref: path })
    router.push(path)
  }
  const prefetchPath = (path: string) => {
    router.prefetch(path)
  }
  const navigateParent = (path: string) => {
    navigateTo(path)
  }
  const handleParentTitleClick = (key: string) => {
    setOpenKeys((keys) => keys.includes(key) ? keys.filter((openKey) => openKey !== key) : [...keys, key])
  }
  const menuItems = buildMenuItems(mainItems, moduleKey, prefetchPath, navigateParent, handleParentTitleClick)
  const bottomMenuItems = buildMenuItems(bottomItems, moduleKey, prefetchPath, navigateParent, handleParentTitleClick)
  const keyPathMap = buildKeyPathMap(moduleChildren)
  const selectedKey = currentModule
    ? findSelectedKey(moduleChildren, pathname, query)
    : undefined
  const handleOpenChange = (keys: string[]) => {
    setOpenKeys(keys)
  }

  const handleClick: MenuProps['onClick'] = ({ key }) => {
    const path = keyPathMap.get(key)
    if (path) navigateTo(path)
  }

  if (!currentModule) return null

  return (
    <>
    <aside aria-label={`${currentModule.label}侧边栏`} className={`${collapsed ? "w-11" : "w-56"} bg-[var(--color-canvas)] border-r border-[var(--color-hairline)] flex flex-col shrink-0 overflow-y-auto transition-[width] duration-200 motion-reduce:transition-none`}>
      <button
        type="button"
        onClick={toggleCollapsed}
        aria-label={collapsed ? "展开侧边栏" : "收起侧边栏"}
        aria-expanded={!collapsed}
        title={collapsed ? "展开侧边栏" : "收起侧边栏，扩大页面显示区域"}
        className={`m-2 inline-flex min-h-8 items-center justify-center gap-2 rounded-[var(--rounded-sm)] text-[var(--color-steel)] hover:bg-[var(--color-surface)] hover:text-[var(--color-primary)] focus-visible:outline-2 focus-visible:outline-[var(--color-primary)] ${collapsed ? "w-7" : "self-end px-2"}`}
      >
        {collapsed ? <MenuUnfoldOutlined aria-hidden /> : <><MenuFoldOutlined aria-hidden /><span className="text-[12px]">收起</span></>}
      </button>
      {!collapsed && <>
      <div className="px-4 pt-5 pb-3">
        <h2 className="text-[18px] font-semibold text-[var(--color-charcoal)]">
          <Link
            href={currentModule.path}
            aria-label={`返回${currentModule.label}首页`}
            title={`点击返回${currentModule.label}首页`}
            onClick={(event) => {
              if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
              event.preventDefault()
              navigateTo(currentModule.path)
            }}
            onMouseEnter={() => prefetchPath(currentModule.path)}
            onFocus={() => prefetchPath(currentModule.path)}
            className="inline-block rounded-[var(--rounded-sm)] text-inherit cursor-pointer transition-colors hover:text-[var(--color-primary)] hover:underline focus-visible:underline focus-visible:outline-2 focus-visible:outline-[var(--color-primary)] underline-offset-4"
          >
            {currentModule.label}
          </Link>
        </h2>
      </div>

      <Menu
        mode="vertical"
        triggerSubMenuAction="hover"
        selectedKeys={selectedKey ? [selectedKey] : []}
        openKeys={openKeys}
        onOpenChange={handleOpenChange}
        items={menuItems}
        onClick={handleClick}
        className="sidebar-menu flex-1"
        style={{ borderInlineEnd: 'none' }}
      />

      {bottomMenuItems.length > 0 && (
        <div className="mt-auto border-t border-[var(--color-hairline-soft)] py-2">
          <Menu
            mode="vertical"
            triggerSubMenuAction="hover"
            selectedKeys={selectedKey ? [selectedKey] : []}
            openKeys={openKeys}
            onOpenChange={handleOpenChange}
            items={bottomMenuItems}
            onClick={handleClick}
            className="sidebar-menu"
            style={{ borderInlineEnd: 'none' }}
          />
        </div>
      )}

      <div className="px-4 py-3 border-t border-[var(--color-hairline-soft)] flex items-center justify-between">
        <p className="text-[12px] text-[var(--color-stone)]">
          v0.1.1
        </p>
        {user && isSystemAdministrator(user) && (
          <button
            onClick={() => navigateTo("/settings")}
            className="inline-flex min-h-8 items-center gap-1.5 rounded-[var(--rounded-sm)] px-2 text-[12px] font-medium text-[var(--color-stone)] transition-colors hover:bg-[var(--color-surface)] hover:text-[var(--color-primary)]"
            title="系统设置"
          >
            <SettingOutlined style={{ fontSize: 16 }} />
            <span>系统设置</span>
          </button>
        )}
      </div>
      </>}
    </aside>
    {pendingHref && (
      <div
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="pointer-events-none fixed right-4 top-20 z-50 flex min-h-9 max-w-[calc(100vw-2rem)] items-center gap-2 rounded-[var(--rounded-md)] border border-[var(--color-hairline)] bg-[var(--color-canvas)] px-3 py-2 text-[12px] text-[var(--color-steel)] shadow-[0_8px_24px_rgba(18,25,38,0.12)] sm:right-6"
      >
        <LoadingOutlined spin aria-hidden />
        <span>正在打开页面…</span>
      </div>
    )}
    </>
  )
}
