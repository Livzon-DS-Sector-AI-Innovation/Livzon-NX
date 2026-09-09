import { moduleMenus, type SubMenuItem } from '@/lib/menu-config'
import { changePageLevels, type PageEditorGrant, type PageLevel } from '@/lib/page-permission-editor'
import type { components } from '@/types/generated/schema'

type Definition = components['schemas']['PagePermissionDefinitionOut']
export type PermissionTreeNode = {
  page_key: string
  page_name: string
  definition?: Definition
  pageKeys: string[]
  children?: PermissionTreeNode[]
}

/** Build missing menu groups without inventing grants for navigation-only nodes. */
export function buildPermissionTree(definitions: Definition[]): PermissionTreeNode[] {
  const names = new Map<string, string>()
  const collect = (items: SubMenuItem[], parent: string) => items.forEach((item) => {
    const key = `${parent}:${item.key}`
    names.set(key, item.label)
    collect(item.children || [], key)
  })
  moduleMenus.forEach((module) => collect(module.children, module.key))
  const nodes = new Map<string, PermissionTreeNode>()
  const roots: PermissionTreeNode[] = []
  for (const definition of definitions) {
    const parts = definition.page_key.split(':')
    let parent: PermissionTreeNode | undefined
    for (let length = Math.min(2, parts.length); length <= parts.length; length++) {
      const key = parts.slice(0, length).join(':')
      let node = nodes.get(key)
      if (!node) {
        node = { page_key: key, page_name: names.get(key) || parts[length - 1], pageKeys: [] }
        nodes.set(key, node)
        if (parent) (parent.children ||= []).push(node)
        else roots.push(node)
      }
      node.pageKeys.push(definition.page_key)
      if (length === parts.length) {
        node.definition = definition
        node.page_name = definition.page_name
      }
      parent = node
    }
  }
  return roots
}

export function filterAuthorizedTree(nodes: PermissionTreeNode[], grants: Record<string, PageEditorGrant>): PermissionTreeNode[] {
  return nodes.filter((node) => node.pageKeys.some((key) => grants[key]?.permissions.length))
    .map((node) => ({ ...node, children: node.children ? filterAuthorizedTree(node.children, grants) : undefined }))
}

export function changeTreePermission<T extends PageEditorGrant>(
  grants: Record<string, T>, pageKeys: string[], level: PageLevel, checked: boolean,
): Record<string, T> {
  const next = { ...grants }
  for (const key of pageKeys) {
    const grant = grants[key]
    if (!grant) continue
    const permissions = changePageLevels(grant.permissions, checked
      ? [...new Set([...grant.permissions, level])]
      : grant.permissions.filter((value) => value !== level))
    next[key] = { ...grant, permissions, sensitiveActions: permissions.includes('operate') ? grant.sensitiveActions : [] }
  }
  return next
}
