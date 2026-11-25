'use client'

// 车间注册表加载：优先读取后端 /equipment/workshops（车间管理页维护），
// 请求失败或未返回数据时回落到写死的 EQUIPMENT_WORKSHOPS 常量——
// 后端不可用/接口异常时页面仍可用。设备页面未挂模块级 React Query
// Provider，故用模块级缓存 + useState/useEffect 而非 useQuery。

import { useEffect, useState } from 'react'
import { EQUIPMENT_WORKSHOPS } from '@/lib/menu-config'
// 瘦身后内联车间摘要类型（原 types/equipment-workshops 已删）
interface WorkshopSummary {
  code: string
  name: string
  is_enabled: boolean
}

const FALLBACK: WorkshopSummary[] = EQUIPMENT_WORKSHOPS.map((ws) => ({
  code: ws.code,
  name: ws.label,
  is_enabled: true,
}))

let cache: WorkshopSummary[] | null = null
let inflight: Promise<WorkshopSummary[]> | null = null

interface WorkshopApiRow {
  code?: unknown
  name?: unknown
  is_enabled?: unknown
}

/** 拉取启用车间清单（带模块级缓存；force 强制刷新）。失败回落常量。 */
export function loadEquipmentWorkshops(force = false): Promise<WorkshopSummary[]> {
  if (!force && cache) return Promise.resolve(cache)
  if (!force && inflight) return inflight
  // 车间注册表以后端为准（汇总页与各车间切换块共用同一份清单）；
  // 接口异常时回落常量，页面仍可用。
  const request = fetch('/api/v1/equipment/workshops')
    .then(async (response) => {
      if (!response.ok) throw new Error(`车间清单请求失败: ${response.status}`)
      const json = (await response.json()) as { data?: WorkshopApiRow[] }
      const rows = Array.isArray(json.data) ? json.data : []
      const items = rows
        .filter((row): row is WorkshopApiRow & { code: string } =>
          Boolean(row && typeof row.code === 'string' && row.code),
        )
        .map((row) => ({
          code: row.code,
          name: typeof row.name === 'string' && row.name ? row.name : row.code,
          is_enabled: row.is_enabled !== false,
        }))
      return items.length ? items : FALLBACK
    })
    .catch(() => FALLBACK)
    .then((items) => {
      cache = items
      inflight = null
      return items
    })
  inflight = request
  return request
}

/** 使缓存失效（车间管理页保存后调用，让其他入口拿到最新清单）。 */
export function invalidateEquipmentWorkshops(): void {
  cache = null
  inflight = null
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
