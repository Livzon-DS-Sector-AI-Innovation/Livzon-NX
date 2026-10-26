'use client'

// 车间注册表加载：优先读取后端 /equipment/workshops（车间管理页维护），
// 请求失败或未返回数据时回落到写死的 EQUIPMENT_WORKSHOPS 常量——
// 后端不可用/接口异常时页面仍可用。设备页面未挂模块级 React Query
// Provider，故用模块级缓存 + useState/useEffect 而非 useQuery。

import { useEffect, useState } from 'react'
import { EQUIPMENT_WORKSHOPS } from '@/lib/menu-config'
import type { WorkshopSummary } from '@/types/equipment-workshops'

const FALLBACK: WorkshopSummary[] = EQUIPMENT_WORKSHOPS.map((ws) => ({
  code: ws.code,
  name: ws.label,
  is_enabled: true,
}))

let cache: WorkshopSummary[] | null = null
let inflight: Promise<WorkshopSummary[]> | null = null

/** 拉取启用车间清单（带模块级缓存；force 强制刷新）。失败回落常量。 */
export function loadEquipmentWorkshops(force = false): Promise<WorkshopSummary[]> {
  if (!force && cache) return Promise.resolve(cache)
  if (!force && inflight) return inflight
  inflight = import('@/lib/api/equipment-workshops')
    .then(async ({ fetchEquipmentWorkshops }) => {
      const workshops = await fetchEquipmentWorkshops()
      cache = workshops.length > 0 ? workshops : null
      return workshops.length > 0 ? workshops : FALLBACK
    })
    .catch(() => FALLBACK)
    .finally(() => {
      inflight = null
    })
  return inflight
}

/** 使缓存失效（车间管理页保存后调用，让其他入口拿到最新清单）。 */
export function invalidateEquipmentWorkshops(): void {
  cache = null
}

/** 客户端钩子：挂载时加载车间清单，未就绪/失败时先渲染兜底常量。 */
export function useEquipmentWorkshops(): WorkshopSummary[] {
  const [workshops, setWorkshops] = useState<WorkshopSummary[]>(
    () => cache ?? FALLBACK,
  )
  useEffect(() => {
    let alive = true
    void loadEquipmentWorkshops().then((items) => {
      if (alive) setWorkshops(items)
    })
    return () => {
      alive = false
    }
  }, [])
  return workshops
}
