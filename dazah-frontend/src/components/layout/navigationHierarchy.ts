import type { ModuleMenu, SubMenuItem } from "@/lib/menu-config"

export interface NavigationLevel {
  label: string
  path?: string
  options?: Array<{ label: string; path: string }>
}

function collectMenuOptions(items: SubMenuItem[]): Array<{ label: string; path: string }> {
  return items.flatMap((item) => item.disabled
    ? []
    : [
        ...(item.path ? [{ label: item.label, path: item.path }] : []),
        ...(item.children ? collectMenuOptions(item.children) : []),
      ])
}

function findMenuTrail(items: SubMenuItem[], pathname: string, ancestors: NavigationLevel[] = []): NavigationLevel[] | undefined {
  let best: NavigationLevel[] | undefined
  for (const item of items) {
    if (item.disabled) continue
    const level: NavigationLevel = {
      label: item.label,
      path: item.path || undefined,
      options: !item.path && item.children ? collectMenuOptions(item.children) : undefined,
    }
    const trail = [...ancestors, level]
    if (item.path) {
      const path = item.path.split("?")[0]
      if (pathname === path || pathname.startsWith(`${path}/`)) {
        if (!best || path.length > (best.at(-1)?.path?.split("?")[0].length || 0)) best = trail
      }
    }
    const child = item.children && findMenuTrail(item.children, pathname, trail)
    if (child && (!best || (child.at(-1)?.path?.length || 0) > (best.at(-1)?.path?.length || 0))) best = child
  }
  return best
}

function firstAccessiblePath(items: SubMenuItem[]): string | undefined {
  for (const item of items) {
    if (item.disabled) continue
    if (item.path) return item.path
    const child = item.children && firstAccessiblePath(item.children)
    if (child) return child
  }
}

export function getNavigationHierarchy(module: ModuleMenu, pathname: string): {
  levels: NavigationLevel[]
  modulePath: string
} {
  const modulePath = module.children.some((item) => item.path === module.path)
    ? module.path
    : firstAccessiblePath(module.children) || module.path
  const trail = findMenuTrail(module.children, pathname) || []
  const matchedPath = trail.at(-1)?.path?.split("?")[0]
  const isDetail = Boolean(matchedPath && pathname !== matchedPath && pathname.startsWith(`${matchedPath}/`))
  const isUnlistedPage = trail.length === 0 && pathname !== modulePath
  const levels: NavigationLevel[] = [
    { label: module.label, path: modulePath },
    ...trail.filter((level, index) => !(index === 0 && level.path === modulePath)),
    ...(isDetail || isUnlistedPage ? [{ label: "详情" }] : []),
  ]
  return { levels, modulePath }
}
