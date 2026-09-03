import type { components } from '@/types/generated/schema'
import { getPermissionModuleName } from '@/lib/menu-config'

export type PageLevel = 'access' | 'query' | 'operate'
// Temporarily hide the editor, retaining stored scope facts and server checks.
export const PAGE_DATA_SCOPE_VISIBLE = false

export function highRiskPageKeys(definitions: components['schemas']['PagePermissionDefinitionOut'][]): string[] {
  return definitions.filter((page) => page.sensitive_actions?.length).map((page) => page.page_key)
}
const levels: PageLevel[] = ['access', 'query', 'operate']

/** Selecting a higher level adds prerequisites; removing one removes dependents. */
export function changePageLevels(previous: PageLevel[], selected: PageLevel[]): PageLevel[] {
  const removed = levels.findIndex((level) => previous.includes(level) && !selected.includes(level))
  if (removed >= 0) return levels.slice(0, removed).filter((level) => selected.includes(level))
  const highest = Math.max(-1, ...selected.map((level) => levels.indexOf(level)))
  return levels.slice(0, highest + 1)
}

export type PageEditorGrant = {
  mode?: 'inherit' | 'custom'
  permissions: PageLevel[]
  sensitiveActions: string[]
  scopeType: string
  departmentIds: string[]
}

export type PageGrantChange = { pageKey: string; pageName: string; before: string; after: string }

export function pageGrantChanges(
  definitions: components['schemas']['PagePermissionDefinitionOut'][],
  before: Record<string, PageEditorGrant>,
  after: Record<string, PageEditorGrant>,
  departmentNames: Map<string, string>,
): PageGrantChange[] {
  const levels = { access: '访问', query: '查询', operate: '操作' }
  const scopes: Record<string, string> = {
    department_tree: '本部门及下级', departments: '指定部门及下级',
    all: '全部部门', self: '仅本人', not_applicable: '不适用',
  }
  const signature = (grant: PageEditorGrant) => JSON.stringify({
    ...grant, permissions: [...grant.permissions].sort(),
    sensitiveActions: [...grant.sensitiveActions].sort(),
    departmentIds: grant.scopeType === 'departments' ? [...grant.departmentIds].sort() : [],
  })
  return definitions.flatMap((definition) => {
    const oldGrant = before[definition.page_key]
    const newGrant = after[definition.page_key]
    if (!oldGrant || !newGrant || signature(oldGrant) === signature(newGrant)) return []
    const describe = (grant: PageEditorGrant) => [
      grant.mode === 'inherit' ? '角色基线' : grant.mode === 'custom' ? '用户覆盖' : '角色授权',
      grant.permissions.length ? grant.permissions.map((level) => levels[level]).join('、') : '无权限',
      PAGE_DATA_SCOPE_VISIBLE ? scopes[grant.scopeType] || '未配置范围' : '',
      PAGE_DATA_SCOPE_VISIBLE && grant.scopeType === 'departments' ? grant.departmentIds.map((id) => departmentNames.get(id) || '已失效部门').join('、') : '',
      ...grant.sensitiveActions.map((key) => definition.sensitive_actions?.find((action) => action.key === key)?.name || '已失效业务动作'),
    ].filter(Boolean).join('；')
    return [{ pageKey: definition.page_key,
      pageName: `${getPermissionModuleName(definition.module_code)} · ${definition.page_name}`,
      before: describe(oldGrant), after: describe(newGrant) }]
  })
}
