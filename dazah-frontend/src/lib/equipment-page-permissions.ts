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

// Internal request context written by the proxy, independently of the actual page path.
export const EQUIPMENT_CONSOLE_MODULE_HEADER = 'X-Dazah-Equipment-Module'

/**
 * 统一工作台的功能模块（展示顺序即数组顺序）：左侧菜单各占一项，
 * module 对应 /equipment?module= 参数，key 即页面授权 key。
 * 备件/人员模块已下线，权限 key 保留；设备检修沿用原「维护」授权 key
 * （equipment:maintenance），无需重新授权。
 */
export const EQUIPMENT_MODULES = [
  { module: 'inspection', key: 'equipment:inspection', label: '设备巡检' },
  { module: 'maintenance', key: 'equipment:maintenance', label: '设备检修' },
  { module: 'assets', key: 'equipment:assets', label: '设备台账' },
] as const

export type EquipmentModule = (typeof EQUIPMENT_MODULES)[number]['module']

/** URL ?module= 参数是否为已知功能模块。 */
export function isEquipmentModule(
  value: string | null | undefined,
): value is EquipmentModule {
  return EQUIPMENT_MODULES.some((item) => item.module === value)
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
  return EQUIPMENT_MODULES.some((item) => hasEquipmentPageAccess(user, item.key))
}

/** 当前用户可进入的首个功能模块（按菜单顺序）；未带 ?module= 进入工作台时的落地模块。 */
export function firstAccessibleEquipmentModule(
  user: EquipmentPermissionUser | null | undefined,
): EquipmentModule {
  return (
    EQUIPMENT_MODULES.find((item) => hasEquipmentPageAccess(user, item.key))?.module
    ?? EQUIPMENT_MODULES[0].module
  )
}

/** 当前用户可查询（access + query）的功能模块；无查询权限时页面只呈现访问提示。 */
export function getQueryableEquipmentTabs(user: EquipmentPermissionUser | null | undefined) {
  if (user?.role === 'admin') return EQUIPMENT_MODULES
  const grants = expandedGrants(user)
  return EQUIPMENT_MODULES.filter(({ key }) => grants.some((grant) =>
    grant.page_key === key && grant.permissions?.includes('access') && grant.permissions.includes('query'),
  ))
}
