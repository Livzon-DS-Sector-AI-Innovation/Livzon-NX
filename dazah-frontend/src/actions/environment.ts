'use server'

import { getServerApiBaseUrl } from '@/lib/server-api'
const API_BASE = getServerApiBaseUrl()

export async function fetchModuleInfoAction() {
  const res = await fetch(`${API_BASE}/api/v1/environment/`, { cache: 'no-store' })
  if (!res.ok) throw new Error('获取模块信息失败')
  return res.json()
}
