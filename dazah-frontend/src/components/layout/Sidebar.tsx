"use client"

import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { useEffect, useMemo, useState } from "react"
import { Menu } from "antd"
import type { MenuProps } from "antd"
import type { ModuleMenu, SubMenuItem } from "@/lib/menu-config"
import { LoadingOutlined, SettingOutlined } from "@ant-design/icons"
import type { User } from "@/types/user"

type MenuItem = Required<MenuProps>['items'][number]

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
  prefetchPath?: (path: string) => void,
  onParentNavigate?: (path: string) => void,
): MenuItem[] {
  return items.map((item) => {
    if (item.children && item.children.length > 0) {
      const label =
        item.path && !item.disabled ? (
          <span
            className="w-full"
            onClick={(event) => {
              // 点击父级标签导航到其仪表盘/落地页（不触发展开切换）
              event.stopPropagation()
              onParentNavigate?.(item.path)
            }}
            onMouseEnter={() => prefetchPath?.(item.path)}
          >
            {item.label}
          </span>
        ) : (
          item.label
        )
      return {
        key: item.key,
        label,
        children: buildMenuItems(item.children, prefetchPath, onParentNavigate),
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

// ── 收集选中路径的所有祖先 key（用于 auto-open）──
function collectAncestorKeys(
  items: SubMenuItem[],
  pathname: string,
  query: URLSearchParams,
): string[] {
  for (const item of items) {
    if (item.children && item.children.length > 0) {
      if (containsPath(item.children, pathname, query)) {
        return [item.key, ...collectAncestorKeys(item.children, pathname, query)]
      }
    }
  }
  return []
}

function containsPath(
  items: SubMenuItem[],
  pathname: string,
  query: URLSearchParams,
): boolean {
  for (const item of items) {
    if (item.children && item.children.length > 0) {
      if (containsPath(item.children, pathname, query)) return true
    } else if (!item.disabled && item.path && matchesMenuPath(item.path, pathname, query)) {
      return true
    }
  }
  return false
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
  const pendingHref = pendingNavigation?.fromHref === currentHref
    ? pendingNavigation.targetHref
    : null
  const [openKeys, setOpenKeys] = useState<string[]>(() =>
    currentModule ? collectAncestorKeys(currentModule.children, pathname, query) : []
  )

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
  const prefetchPath = (path: string) => {
    router.prefetch(withAuthToken(path))
  }
  const withAuthToken = (path: string) => {
    const token = searchParams.get("auth_token")
    if (!token) return path
    const [pathname, queryString = ""] = path.split("?")
    const params = new URLSearchParams(queryString)
    if (!params.has("auth_token")) {
      params.set("auth_token", token)
    }
    const nextQuery = params.toString()
    return `${pathname}${nextQuery ? `?${nextQuery}` : ""}`
  }
  const navigateParent = (path: string) => {
    router.push(withAuthToken(path))
  }
  const menuItems = buildMenuItems(mainItems, prefetchPath, navigateParent)
  const bottomMenuItems = buildMenuItems(bottomItems, prefetchPath, navigateParent)
  const keyPathMap = buildKeyPathMap(moduleChildren)
  const selectedKey = currentModule
    ? findSelectedKey(moduleChildren, pathname, query)
    : undefined
  const handleOpenChange = (keys: string[]) => {
    setOpenKeys(keys)
  }

  const navigateTo = (path: string) => {
    const href = withAuthToken(path)
    if (href === currentHref) return
    setPendingNavigation({ fromHref: currentHref, targetHref: href })
    router.push(href)
  }

  const handleClick: MenuProps['onClick'] = ({ key }) => {
    const path = keyPathMap.get(key)
    if (path) navigateTo(path)
  }

  if (!currentModule) return null

  return (
    <aside className="w-56 bg-[var(--color-canvas)] border-r border-[var(--color-hairline)] flex flex-col shrink-0 overflow-y-auto">
      <div
        className={`px-4 pt-5 pb-3${moduleKey === "safety" ? " cursor-pointer group" : ""}`}
        onClick={moduleKey === "safety" ? () => navigateTo(currentModule.path) : undefined}
      >
        <h2
          className={`text-[18px] font-semibold text-[var(--color-charcoal)]${
            moduleKey === "safety" ? " group-hover:text-[var(--color-primary)] transition-colors" : ""
          }`}
        >
          {currentModule.label}
        </h2>
      </div>

      {pendingHref && (
        <div
          role="status"
          aria-live="polite"
          className="mx-3 mb-2 flex min-h-8 items-center gap-2 rounded-[var(--rounded-sm)] bg-[var(--color-surface)] px-3 text-[12px] text-[var(--color-steel)]"
        >
          <LoadingOutlined spin aria-hidden />
          <span>正在打开页面…</span>
        </div>
      )}

      <Menu
        mode="inline"
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
            mode="inline"
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
        {user?.role === "admin" && (
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
    </aside>
  )
}
