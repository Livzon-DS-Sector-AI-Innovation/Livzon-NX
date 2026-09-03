import { cookies, headers } from 'next/headers'

export async function getServerToken(): Promise<string | undefined> {
  const cookieStore = await cookies()
  const token = cookieStore.get('auth_token')
  return token?.value
}

/** 返回带 Authorization 的 headers 对象，供 Server Actions 调用后端 API */
export async function getAuthHeaders(): Promise<Record<string, string>> {
  const authHeaders: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  const [cookieStore, requestHeaders] = await Promise.all([cookies(), headers()])
  const token = cookieStore.get('auth_token')?.value
  const rawCookie = requestHeaders.get('cookie')
  const pagePath = requestHeaders.get('X-Dazah-Page-Path')
  if (pagePath) authHeaders['X-Dazah-Page-Path'] = pagePath
  const rawToken = rawCookie?.match(/(?:^|;\s*)auth_token=([^;]+)/)?.[1]

  // Prefer a standard Bearer header from Next.js' parsed cookie store. Raw
  // Cookie forwarding is only a fallback for request contexts where cookies()
  // is unavailable or empty.
  if (token) {
    authHeaders.Authorization = `Bearer ${token}`
  } else if (rawToken) {
    let fallbackToken = rawToken
    try {
      fallbackToken = decodeURIComponent(rawToken)
    } catch {
      // Keep the original value when the cookie is not percent-encoded.
    }
    authHeaders.Authorization = `Bearer ${fallbackToken}`
  }
  return authHeaders
}
