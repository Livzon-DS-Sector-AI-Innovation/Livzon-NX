'use client'

import type {
  WorkshopAdminSummary,
  WorkshopCreateRequest,
  WorkshopSummary,
  WorkshopUpdateRequest,
} from '@/types/equipment-workshops'

const BASE = '/api/v1/equipment/workshops'

interface PageResult<T> {
  code: number
  message?: string
  data: T
}

async function getJson<T>(url: string): Promise<PageResult<T>> {
  const response = await fetch(url)
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.message || `请求失败: ${response.status}`)
  }
  return response.json()
}

async function writeJson<T>(
  url: string,
  method: 'POST' | 'PUT',
  body: unknown,
): Promise<PageResult<T>> {
  const response = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const json = await response.json().catch(() => null)
  if (!response.ok || !json || json.code !== 200) {
    throw new Error(json?.message || `请求失败（HTTP ${response.status}）`)
  }
  return json
}

/** 启用车间清单（工作台与飞书配置页数据源） */
export async function fetchEquipmentWorkshops(): Promise<WorkshopSummary[]> {
  const json = await getJson<WorkshopSummary[]>(BASE)
  return json.data ?? []
}

/** 全部车间清单（含停用，车间管理页） */
export async function fetchAllEquipmentWorkshops(): Promise<
  WorkshopAdminSummary[]
> {
  const json = await getJson<WorkshopAdminSummary[]>(`${BASE}/all`)
  return json.data ?? []
}

/** 新增车间（代码重复/格式非法时后端返回 4xx） */
export async function createEquipmentWorkshop(
  values: WorkshopCreateRequest,
): Promise<WorkshopAdminSummary> {
  const json = await writeJson<WorkshopAdminSummary>(BASE, 'POST', values)
  return json.data
}

/** 更新车间（改名/启停；代码不可改） */
export async function updateEquipmentWorkshop(
  code: string,
  values: WorkshopUpdateRequest,
): Promise<WorkshopAdminSummary> {
  const json = await writeJson<WorkshopAdminSummary>(
    `${BASE}/${encodeURIComponent(code)}`,
    'PUT',
    values,
  )
  return json.data
}
