import { expandEquipmentPagePermissions, getPageKeyByPath, type ModuleMenu, type SubMenuItem } from '@/lib/menu-config'
import type { User } from '@/types/user'
import type { components } from '@/types/generated/schema'
import { isSystemAdministrator } from '@/lib/administrator-role'

export interface TodoSource {
  key: string
  label: string
  path: string
  apiPath: string
  kind: 'business'
}

export interface TodoGroup {
  source: TodoSource
  total: number
  items: { id: string; title: string; detail: string; due_date?: string | null }[]
  error?: string
}

const businessTodoPages: Record<string, {
  moduleCode: string
  kind: string
  /** 聚合入口（如设备统一工作台）按具体功能页 key 校验授权 */
  pageKey?: string
  /** 待办点击跳转地址与菜单入口不同时显式指定 */
  todoPath?: string
}> = {
  '/quality/deviations/ledger': { moduleCode: 'quality', kind: 'deviations' },
  '/quality/capas/ledger': { moduleCode: 'quality', kind: 'capas' },
  '/quality/capas/plans': { moduleCode: 'quality', kind: 'capa-plans' },
  '/quality/change/action-plans': { moduleCode: 'quality', kind: 'change-plans' },
  '/equipment': {
    moduleCode: 'equipment',
    kind: 'maintenance',
    pageKey: 'equipment:maintenance',
    todoPath: '/equipment?module=maintenance',
  },
  '/safety/hazard-ledger': { moduleCode: 'safety', kind: 'hazards' },
  '/safety/accident': { moduleCode: 'safety', kind: 'accidents' },
  '/safety/check': { moduleCode: 'safety', kind: 'checks' },
  '/registration/declaration-progress/international-planned-in-progress': { moduleCode: 'registration', kind: 'validation-audits' },
  '/hr/training/plan-tracking': { moduleCode: 'hr', kind: 'plan-tracking' },
  '/hr/position-transfer': { moduleCode: 'hr', kind: 'position-transfer' },
}

// Visibility alone is insufficient. Business adapters determine the current
// responsible person and data range; approvals also require approve permission.
export function getTodoSources(user: User, modules: ModuleMenu[]): TodoSource[] {
  if (isSystemAdministrator(user)) return []
  const grants = expandEquipmentPagePermissions(user.page_permissions)
  const sources = new Map<string, TodoSource>()
  const visit = (items: SubMenuItem[], labels: string[]) => {
    for (const item of items) {
      if (item.disabled || (item.adminOnly && user.role !== 'admin')) continue
      const key = getPageKeyByPath(item.path)
      const business = businessTodoPages[item.path]
      const grantKey = business?.pageKey ?? key
      const grant = grants.find((entry) => entry.page_key === grantKey)
      const canOperate = user.role === 'admin' ||
        ['access', 'query', 'operate'].every((permission) => grant?.permissions?.some((value) => value === permission))
      const canApprove = user.role === 'admin' || Boolean(grant?.sensitive_actions?.includes('approve'))
      const approval = item.path === '/hr/position-transfer'
      if (grantKey && business && canOperate && (!approval || canApprove)) {
        const params = new URLSearchParams({ page: '1', page_size: '5' })
        params.set('kind', business.kind)
        sources.set(grantKey, {
          key: grantKey, label: business?.kind === 'validation-audits' ? '注册管理 / 验证文件审核' : [...labels, item.label].join(' / '),
          path: business?.todoPath
            ?? (business?.kind === 'validation-audits' ? '/registration/validation-audit' : item.path),
          kind: 'business',
          apiPath: `/api/v1/${business.moduleCode}/my-todos?${params}`,
        })
      }
      visit(item.children || [], [...labels, item.label])
    }
  }
  for (const moduleMenu of modules) visit(moduleMenu.children, [moduleMenu.label])
  return [...sources.values()]
}

async function fetchTodoGroup(source: TodoSource, signal?: AbortSignal): Promise<TodoGroup> {
  const response = await fetch(source.apiPath, {
    cache: 'no-store', signal,
    headers: { 'X-Dazah-Page-Key': source.key, 'X-Dazah-Page-Path': source.path },
  })
  if (!response.ok) throw new Error(response.status === 403 ? '权限已变化，请刷新页面确认授权' : '待办暂时无法读取，请重试')
  const data: components['schemas']['BusinessTodoPage'] = await response.json()
  return { source, total: data.total, items: data.items }
}

export async function fetchMyTodos(sources: TodoSource[], signal?: AbortSignal): Promise<TodoGroup[]> {
  const groups: TodoGroup[] = []
  // Bound parallel reads so users with many business grants do not exhaust
  // the backend connection pool.
  for (let index = 0; index < sources.length; index += 4) {
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')
    const batch = sources.slice(index, index + 4)
    const results = await Promise.allSettled(batch.map((source) => fetchTodoGroup(source, signal)))
    results.forEach((result, offset) => groups.push(result.status === 'fulfilled' ? result.value : {
      source: batch[offset], total: 0, items: [],
      error: result.reason instanceof Error ? result.reason.message : '待办读取失败',
    }))
  }
  return groups
}
