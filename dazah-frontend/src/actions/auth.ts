'use server'

import { getBackendFallbackUrls } from '@/lib/server-api'
import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import { revalidatePath } from 'next/cache'
import type { User } from '@/types/user'
import { getAuthHeaders } from '@/lib/auth'

export interface LoginActionState {
  error?: string
}

function getErrorMessage(value: unknown): string {
  if (!value || typeof value !== 'object') return '登录失败，请重试'
  const payload = value as { message?: string; detail?: string }
  return payload.detail || payload.message || '登录失败，请重试'
}

async function fetchBackend(path: string, options?: RequestInit) {
  let lastError: unknown
  const attemptedUrls: string[] = []
  for (const baseUrl of getBackendFallbackUrls()) {
    const url = `${baseUrl}${path}`
    attemptedUrls.push(url)
    try {
      return await fetch(url, {
        ...options,
        cache: 'no-store',
      })
    } catch (error) {
      lastError = error
    }
  }

  const cause =
    lastError instanceof Error ? lastError.message : 'unknown network error'
  throw new Error(
    `无法连接后端服务，已尝试：${attemptedUrls.join('、')}。最后错误：${cause}`
  )
}

export async function getCurrentUser(): Promise<User | null> {
  try {
    const res = await fetchBackend('/api/v1/identity/me', {
      headers: await getAuthHeaders(),
    })
    if (!res.ok) return null
    const json = await res.json()
    return json.data ?? null
  } catch {
    return null
  }
}

export async function loginWithPassword(
  _prevState: LoginActionState,
  formData: FormData
): Promise<LoginActionState> {
  const username = String(formData.get('username') || '').trim()
  const password = String(formData.get('password') || '')
  let token: string | null = null

  if (!username || !password) {
    return { error: '请输入用户名和密码' }
  }

  try {
    const res = await fetchBackend('/api/v1/identity/auth/local/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })

    const json = await res.json().catch(() => null)
    if (!res.ok) {
      return { error: getErrorMessage(json) }
    }

    token = json?.data?.access_token
    if (!token) {
      return { error: '登录响应缺少 token，请检查后端接口' }
    }
  } catch (error) {
    return {
      error:
        error instanceof Error
          ? error.message
          : '网络异常，请稍后重试',
    }
  }

  redirect(`/auth/callback?token=${encodeURIComponent(token)}&next=%2Fproduction`)
}

export async function logout() {
  const cookieStore = await cookies()
  cookieStore.delete('auth_token')
  revalidatePath('/')
  redirect('/login')
}
