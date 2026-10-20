import type { AuthUser } from '@/stores/auth'

/**
 * 设备模块页面 key（收敛后）：功能页单页 + 车间切换，车间可见性由
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

type EquipmentPermissionUser = Pick<AuthUser, 'id' | 'role'> & {
  page_permissions?: ReadonlyArray<{
    page_key: string
    permissions?: ReadonlyArray<'access' | 'query' | 'operate'>
    visible_sections?: ReadonlyArray<string> | null
  }>
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
  const grant = (user.page_permissions ?? []).find((g) => g.page_key === pageKey)
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

/** 用户是否可进入指定功能页（admin 或持有 access 授权）。 */
export function hasEquipmentPageAccess(
  user: EquipmentPermissionUser | null | undefined,
  pageKey: EquipmentPageKey,
): boolean {
  if (!user) return false
  if (user.role === 'admin') return true
  return (user.page_permissions ?? []).some(
    (grant) => grant.page_key === pageKey && grant.permissions?.includes('access'),
  )
}
