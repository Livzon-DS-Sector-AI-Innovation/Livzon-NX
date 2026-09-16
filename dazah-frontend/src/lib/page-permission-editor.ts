import type { components } from '@/types/generated/schema'
import { getPermissionModuleName } from '@/lib/menu-config'

export type PageLevel = 'access' | 'query' | 'operate'
export type PagePermissionTier = 'none' | PageLevel
export const PAGE_DATA_SCOPE_VISIBLE = true

export const pagePermissionTierOptions: Array<{
  value: PagePermissionTier
  label: string
  description: string
}> = [
  { value: 'none', label: '无权限', description: '不能进入该页面' },
  { value: 'access', label: '仅入口', description: '可以进入页面，但不读取业务数据' },
  { value: 'query', label: '可查看', description: '可以查看授权范围内的数据' },
  { value: 'operate', label: '普通操作', description: '可以新增或修改常规业务数据；不包含需要单独授权的高风险操作' },
]

export function pagePermissionTier(permissions: PageLevel[]): PagePermissionTier {
  if (permissions.includes('operate')) return 'operate'
  if (permissions.includes('query')) return 'query'
  if (permissions.includes('access')) return 'access'
  return 'none'
}

export function permissionsForTier(tier: PagePermissionTier): PageLevel[] {
  if (tier === 'operate') return ['access', 'query', 'operate']
  if (tier === 'query') return ['access', 'query']
  if (tier === 'access') return ['access']
  return []
}

export function pagePermissionTierLabel(permissions: PageLevel[]): string {
  return pagePermissionTierOptions.find((option) => option.value === pagePermissionTier(permissions))?.label || '无权限'
}

export function pageScopeSummary(
  scopeType: string,
  departmentIds: string[],
  departmentNames: Map<string, string> = new Map(),
): string {
  if (scopeType === 'all') return '全部部门'
  if (scopeType === 'self') return '仅本人'
  if (scopeType === 'department_tree') return '本部门及下级'
  if (scopeType === 'not_applicable') return '不适用'
  if (scopeType !== 'departments') return '未配置范围'
  const names = departmentIds.map((id) => departmentNames.get(id)).filter(Boolean) as string[]
  if (names.length === departmentIds.length && names.length <= 3) return `指定部门：${names.join('、')}`
  return `指定 ${departmentIds.length} 个部门`
}

export function pageScopeIssue(
  scopeType: string,
  departmentIds: string[],
  supportedScopeTypes: string[],
  activeDepartmentIds: Set<string>,
): string | undefined {
  if (!supportedScopeTypes.includes(scopeType)) return '当前数据范围已不再受此页面支持'
  if (scopeType !== 'departments') return undefined
  if (!departmentIds.length) return '指定部门范围至少选择一个部门'
  const missing = departmentIds.filter((id) => !activeDepartmentIds.has(id))
  return missing.length ? `包含 ${missing.length} 个已失效部门，请重新选择` : undefined
}

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
  sensitiveActionsExpiresAt?: string | null
  scopeType: string
  departmentIds: string[]
}

export type PageGrantChangeKind = 'grant' | 'expand' | 'restrict' | 'revoke' | 'mixed' | 'source'
export type PageGrantChange = {
  pageKey: string
  pageName: string
  before: string
  after: string
  kind: PageGrantChangeKind
}

function grantFacts(grant: PageEditorGrant): Set<string> {
  return new Set([
    ...grant.permissions.map((permission) => `permission:${permission}`),
    ...grant.sensitiveActions.map((action) => `action:${action}`),
  ])
}

export function pageGrantChangeKind(before: PageEditorGrant, after: PageEditorGrant): PageGrantChangeKind {
  const previous = grantFacts(before)
  const next = grantFacts(after)
  const added = [...next].some((fact) => !previous.has(fact))
  const removed = [...previous].some((fact) => !next.has(fact))
  if (added && !removed) return previous.size ? 'expand' : 'grant'
  if (removed && !added) return next.size ? 'restrict' : 'revoke'
  if (added || removed || before.scopeType !== after.scopeType ||
    before.sensitiveActionsExpiresAt !== after.sensitiveActionsExpiresAt ||
    JSON.stringify([...before.departmentIds].sort()) !== JSON.stringify([...after.departmentIds].sort())) return 'mixed'
  return 'source'
}

export function pageGrantChanges(
  definitions: components['schemas']['PagePermissionDefinitionOut'][],
  before: Record<string, PageEditorGrant>,
  after: Record<string, PageEditorGrant>,
  departmentNames: Map<string, string>,
): PageGrantChange[] {
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
      pagePermissionTierLabel(grant.permissions),
      PAGE_DATA_SCOPE_VISIBLE ? scopes[grant.scopeType] || '未配置范围' : '',
      PAGE_DATA_SCOPE_VISIBLE && grant.scopeType === 'departments' ? grant.departmentIds.map((id) => departmentNames.get(id) || '已失效部门').join('、') : '',
      ...grant.sensitiveActions.map((key) => definition.sensitive_actions?.find((action) => action.key === key)?.name || '已失效业务动作'),
      grant.sensitiveActions.length && grant.sensitiveActionsExpiresAt
        ? `到期：${new Date(grant.sensitiveActionsExpiresAt).toLocaleString('zh-CN')}` : '',
    ].filter(Boolean).join('；')
    return [{ pageKey: definition.page_key,
      pageName: `${getPermissionModuleName(definition.module_code)} · ${definition.page_name}`,
      before: describe(oldGrant), after: describe(newGrant), kind: pageGrantChangeKind(oldGrant, newGrant) }]
  })
}
