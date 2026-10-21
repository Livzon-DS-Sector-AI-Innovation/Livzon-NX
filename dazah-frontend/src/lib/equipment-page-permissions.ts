import type { AuthUser } from '@/stores/auth'
import {
  expandEquipmentPagePermissions,
  type PageAccessSummary,
} from '@/lib/menu-config'

/**
 * 设备模块页面 key：统一工作台按 ?module= 切换功能模块，车间可见性由
 * page_permissions 的 visible_sections 承载（null = 全部车间可见，
 * 与生产模块 useProductionPermissions 同语义）。
 */
export const EQUIPMENT_PAGE_KEYS = {
  stats: 'equipment:stats',
  assets: 'equipment:assets',
  maintenance: 'equipment:maintenance',
  inspection: 'equipment:inspection',
  spareParts: 'equipment:spare-parts',
  personnel: 'equipment:personnel',
} as const

export type EquipmentPageKey = (typeof EQUIPMENT_PAGE_KEYS)[keyof typeof EQUIPMENT_PAGE_KEYS]

/**
 * 统一工作台内的功能模块 Tab（展示顺序即数组顺序）：
 * module 对应 /equipment?module= 参数，key 即页面授权 key。
 */
export const EQUIPMENT_MODULE_TABS = [
  { module: 'assets', key: 'equipment:assets', label: '设备台账' },
  { module: 'maintenance', key: 'equipment:maintenance', label: '维护保养' },
  { module: 'inspection', key: 'equipment:inspection', label: '设备巡检' },
  { module: 'spare-parts', key: 'equipment:spare-parts', label: '备件管理' },
  { module: 'personnel', key: 'equipment:personnel', label: '人员配置' },
] as const

export type EquipmentModule = (typeof EQUIPMENT_MODULE_TABS)[number]['module']

/** URL ?module= 参数是否为已知功能模块。 */
export function isEquipmentModule(
  value: string | null | undefined,
): value is EquipmentModule {
  return EQUIPMENT_MODULE_TABS.some((tab) => tab.module === value)
}

type EquipmentPermissionUser = Pick<AuthUser, 'id' | 'role'> & {
  page_permissions?: ReadonlyArray<PageAccessSummary> | null
}

/** 展开旧「车间×功能」叶授权后的功能页授权列表。 */
function expandedGrants(
  user: EquipmentPermissionUser | null | undefined,
): PageAccessSummary[] {
  return expandEquipmentPagePermissions([...(user?.page_permissions ?? [])])
}

/**
 * 工单/巡检等待办入口使用功能页 key；管理员与未配置 visible_sections 的
 * 授权默认全部车间可见，配置了列表的仅列表内车间可见。
 */
export function visibleEquipmentWorkshops(
  user: EquipmentPermissionUser | null | undefined,
  pageKey: EquipmentPageKey,
): string[] | null {
  if (!user) return null
  if (user.role === 'admin') return null
  const grant = expandedGrants(user).find((g) => g.page_key === pageKey)
  if (!grant) return null
  if (grant.visible_sections == null) return null
  return [...grant.visible_sections]
}

/** 指定功能页在指定车间是否可见（用于车间切换块过滤）。 */
export function hasEquipmentWorkshopAccess(
  user: EquipmentPermissionUser | null | undefined,
  pageKey: EquipmentPageKey,
  workshopCode: string,
): boolean {
  const visible = visibleEquipmentWorkshops(user, pageKey)
  if (visible == null) return true
  return visible.includes(workshopCode)
}

/** 用户是否可进入指定功能页（admin 或持有 access 授权，含旧叶授权投影）。 */
export function hasEquipmentPageAccess(
  user: EquipmentPermissionUser | null | undefined,
  pageKey: EquipmentPageKey,
): boolean {
  if (!user) return false
  if (user.role === 'admin') return true
  return expandedGrants(user).some(
    (grant) => grant.page_key === pageKey && grant.permissions?.includes('access'),
  )
}

/** 统一工作台可见条件：任一功能模块有 access 授权（admin 恒真）。 */
export function hasAnyEquipmentModuleAccess(
  user: EquipmentPermissionUser | null | undefined,
): boolean {
  return EQUIPMENT_MODULE_TABS.some((tab) => hasEquipmentPageAccess(user, tab.key))
}
