/**
 * 菜单树构建/过滤工具（数据库驱动菜单的唯一树构建器）。
 *
 * TopNav / Sidebar / 菜单管理页共用本文件，禁止各组件自行建树。
 * 输入为后端返回的扁平菜单列表（MenuResponse 形状，snake_case），
 * 输出为父子挂接后的 MenuTreeNode（camelCase UI ViewModel）。
 */

/**
 * 菜单扁平项（与后端 MenuResponse 字段对齐；后端接口返回 JSONResponse，
 * 不产出 OpenAPI schema，故手写 ViewModel，禁止臆造字段）
 */
export interface MenuFlatItem {
  id: string
  key: string | null
  parent_id: string | null
  name: string
  type: string
  permission_code: string | null
  route_path: string | null
  component_path: string | null
  icon: string | null
  sort_order: number
  status: string
}

export interface MenuTreeNode {
  id: string
  key: string | null
  parentId: string | null
  name: string
  type: string
  permissionCode: string | null
  routePath: string | null
  icon: string | null
  sortOrder: number
  status: string
  children: MenuTreeNode[]
}

/** 扁平列表 → 树（按 parent_id 挂接，sort_order 排序；父缺失的节点提升为顶层） */
export function buildMenuTree(items: MenuFlatItem[]): MenuTreeNode[] {
  const byId = new Map<string, MenuTreeNode>()
  for (const item of items) {
    byId.set(item.id, {
      id: item.id,
      key: item.key ?? null,
      parentId: item.parent_id ?? null,
      name: item.name,
      type: item.type,
      permissionCode: item.permission_code ?? null,
      routePath: item.route_path ?? null,
      icon: item.icon ?? null,
      sortOrder: item.sort_order ?? 0,
      status: item.status,
      children: [],
    })
  }

  const roots: MenuTreeNode[] = []
  for (const node of byId.values()) {
    if (node.parentId && byId.has(node.parentId)) {
      byId.get(node.parentId)!.children.push(node)
    } else {
      roots.push(node)
    }
  }

  const sortRecursive = (nodes: MenuTreeNode[]) => {
    nodes.sort((a, b) => a.sortOrder - b.sortOrder)
    for (const n of nodes) sortRecursive(n.children)
  }
  sortRecursive(roots)
  return roots
}

/** 仅保留 active 节点（disabled 节点及其子树整体剔除，保持树完整） */
export function filterActiveMenus(items: MenuFlatItem[]): MenuFlatItem[] {
  const tree = buildMenuTree(items)
  const activeIds = new Set<string>()
  const collectActive = (nodes: MenuTreeNode[]) => {
    for (const node of nodes) {
      if (node.status !== "active") continue
      collectActive(node.children)
      activeIds.add(node.id)
    }
  }
  collectActive(tree)
  return items.filter((item) => activeIds.has(item.id))
}

/** 构建 key → routePath 映射（叶子节点与带 path 的父级均可点击） */
export function buildKeyPathMap(items: MenuTreeNode[]): Map<string, string> {
  const map = new Map<string, string>()
  const visit = (nodes: MenuTreeNode[]) => {
    for (const node of nodes) {
      if (node.routePath) map.set(node.key ?? node.id, node.routePath)
      visit(node.children)
    }
  }
  visit(items)
  return map
}

function isPathMatch(itemPath: string, pathname: string): boolean {
  return pathname === itemPath || pathname.startsWith(itemPath + "/")
}

/** 递归查找当前路径匹配的最佳菜单项（优先最长路径） */
export function findSelectedKey(
  items: MenuTreeNode[],
  pathname: string,
): string | undefined {
  let bestMatch: MenuTreeNode | undefined

  const visit = (nodes: MenuTreeNode[]) => {
    for (const node of nodes) {
      if (node.routePath && isPathMatch(node.routePath, pathname)) {
        if (!bestMatch || node.routePath.length > (bestMatch.routePath?.length ?? 0)) {
          bestMatch = node
        }
      }
      visit(node.children)
    }
  }
  visit(items)
  return bestMatch?.key ?? bestMatch?.id
}

/** 收集选中路径的所有祖先 key（用于 defaultOpenKeys） */
export function collectAncestorKeys(
  items: MenuTreeNode[],
  pathname: string,
): string[] {
  const visit = (nodes: MenuTreeNode[]): string[] => {
    for (const node of nodes) {
      const selfMatch = !!node.routePath && isPathMatch(node.routePath, pathname)
      if (selfMatch || containsPath(node.children, pathname)) {
        return [node.key ?? node.id, ...visit(node.children)]
      }
    }
    return []
  }
  return visit(items)
}

function containsPath(items: MenuTreeNode[], pathname: string): boolean {
  for (const node of items) {
    if (node.routePath && isPathMatch(node.routePath, pathname)) return true
    if (containsPath(node.children, pathname)) return true
  }
  return false
}