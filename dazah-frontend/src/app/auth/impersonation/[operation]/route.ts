import { NextRequest, NextResponse } from 'next/server'
import { IMPERSONATION_COOKIE } from '@/lib/impersonation'
import { getPublicOrigin, isTrustedBrowserWriteRequest } from '@/lib/public-origin'
import { serverApiUrl } from '@/lib/server-api'

export async function POST(request: NextRequest, context: { params: Promise<{ operation: string }> }) {
  const { operation } = await context.params
  if (operation !== 'start' && operation !== 'exit') {
    return NextResponse.json({ message: '操作不存在' }, { status: 404 })
  }
  if (!isTrustedBrowserWriteRequest(request)) {
    return NextResponse.json({ message: '请求来源未经授权' }, { status: 403 })
  }

  const headers = new Headers({
    'Content-Type': 'application/json',
    Origin: getPublicOrigin(request),
    'X-Forwarded-Proto': new URL(getPublicOrigin(request)).protocol.slice(0, -1),
  })
  for (const name of ['x-forwarded-for', 'user-agent']) {
    const value = request.headers.get(name)
    if (value) headers.set(name, value)
  }
  const sessionCookies = ['auth_token', IMPERSONATION_COOKIE].flatMap((name) => {
    const cookie = request.cookies.get(name)
    return cookie ? [`${name}=${encodeURIComponent(cookie.value)}`] : []
  })
  if (sessionCookies.length) headers.set('Cookie', sessionCookies.join('; '))

  try {
    const backend = await fetch(serverApiUrl(`/identity/auth/impersonation/${operation}`), {
      method: 'POST',
      headers,
      body: operation === 'start' ? await request.text() : undefined,
      cache: 'no-store',
      redirect: 'error',
      signal: AbortSignal.timeout(10000),
    })
    const response = new NextResponse(await backend.text(), {
      status: backend.status,
      headers: { 'Cache-Control': 'no-store', 'Content-Type': 'application/json' },
    })
    for (const cookie of backend.headers.getSetCookie()) {
      if (cookie.startsWith(`${IMPERSONATION_COOKIE}=`) || (operation === 'exit' && cookie.startsWith('auth_token='))) {
        response.headers.append('Set-Cookie', cookie)
      }
    }
    return response
  } catch {
    return NextResponse.json({ message: '暂时无法确认身份切换，请稍后重试' }, { status: 503 })
  }
}
