/**
 * 公告通知台账的客户端读取/编辑封装（浏览器经代理访问，Cookie 认证）。
 *
 * 台账元数据对有页面权限者可见；公告内容与原文仅 operate 权限用户
 * 经专用端点获取（后端强约束，前端按钮随权限显隐）。
 */

import type { NoticeContentResponse, NoticeItem, NoticeListResponse, NoticeUpdateInput } from '@/types/administration'

const BASE = '/api/v1/administration/notices'

async function noticeFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    cache: 'no-store',
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
  })
  const body = (await response.json().catch(() => null)) as {
    message?: string
    detail?: string | { message?: string }
    data?: T
  } | null
  if (!response.ok || body === null) {
    const detail = typeof body?.detail === 'string' ? body.detail : body?.detail?.message
    throw new Error(detail || body?.message || `请求失败（${response.status}）`)
  }
  return body.data as T
}

export interface NoticeListParams {
  page?: number
  page_size?: number
  keyword?: string
  category?: string
}

export function fetchNoticeList(params: NoticeListParams): Promise<NoticeListResponse> {
  const query = new URLSearchParams()
  query.set('page', String(params.page ?? 1))
  query.set('page_size', String(params.page_size ?? 20))
  if (params.keyword) query.set('keyword', params.keyword)
  if (params.category) query.set('category', params.category)
  return noticeFetch<NoticeListResponse>(`?${query.toString()}`)
}

export function fetchNoticeDetail(id: string): Promise<NoticeItem> {
  return noticeFetch<NoticeItem>(`/${encodeURIComponent(id)}`)
}

export function fetchNoticeContent(id: string): Promise<NoticeContentResponse> {
  return noticeFetch<NoticeContentResponse>(`/${encodeURIComponent(id)}/content`)
}

/** 原文下载直链（代理注入 Cookie 认证；仅 operate 权限可达）。 */
export function noticeFileUrl(id: string): string {
  return `${BASE}/${encodeURIComponent(id)}/file`
}

export async function updateNotice(
  id: string,
  payload: NoticeUpdateInput,
): Promise<NoticeItem> {
  return noticeFetch<NoticeItem>(`/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export async function deleteNotice(id: string): Promise<void> {
  await noticeFetch<{ deleted: boolean }>(`/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  })
}
