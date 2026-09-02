import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

import { getServerApiBaseUrl } from '@/lib/server-api'
import { isSecurePublicRequest } from '@/lib/public-origin'
import { getModuleByKey, getPageKeyByPath, getAuthorizedPageMenus } from '@/lib/menu-config'
import type { SubMenuItem } from '@/lib/menu-config'
import type { User } from '@/types/user'

const AUTH_COOKIE_MAX_AGE = 60 * 60 * 24

function firstPage(items: SubMenuItem[]): string | undefined {
  for (const item of items) {
    if (item.path && !item.disabled) return item.path
    const nested = item.children && firstPage(item.children)
    if (nested) return nested
  }
}

function denied(message: string, status = 403) {
  return new NextResponse(`<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>页面访问受限</title><body><main><h1>页面访问受限</h1><p>${message}</p><a href="/">返回平台</a></main></body></html>`, {
    status, headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' },
  })
}

export async function proxy(request: NextRequest) {
  const legacyToken = request.nextUrl.searchParams.get('auth_token')
  if (legacyToken) {
    const target = request.nextUrl.clone()
    target.searchParams.delete('auth_token')

    const response = NextResponse.redirect(target)
    response.cookies.set('auth_token', legacyToken, {
      httpOnly: true,
      maxAge: AUTH_COOKIE_MAX_AGE,
      path: '/',
      sameSite: 'lax',
      secure: isSecurePublicRequest(request),
    })
    return response
  }

  if (
    request.nextUrl.pathname.startsWith('/api/v1/') ||
    request.nextUrl.pathname.startsWith('/uploads/')
  ) {
    const target = new URL(request.nextUrl.pathname, getServerApiBaseUrl())
    target.search = request.nextUrl.search

    const requestHeaders = new Headers(request.headers)
    const token = request.cookies.get('auth_token')?.value
    if (token && !requestHeaders.has('Authorization')) {
      requestHeaders.set('Authorization', `Bearer ${token}`)
    }
    const referer = request.headers.get('referer')
    if (referer && !requestHeaders.has('X-Dazah-Page-Path')) {
      try {
        requestHeaders.set('X-Dazah-Page-Path', new URL(referer).pathname)
      } catch {
        // Invalid external Referer is ignored; enforced modules fail closed.
      }
    }

    return NextResponse.rewrite(target, {
      request: {
        headers: requestHeaders,
      },
    })
  }

  const requestHeaders = new Headers(request.headers)
  requestHeaders.set('X-Dazah-Page-Path', request.nextUrl.pathname)
  const currentModule = getModuleByKey(request.nextUrl.pathname.split('/')[1])
  if (currentModule) {
    // This gate runs before the App Router evaluates any child Server Component.
    // Layout-only guards can render concurrently with protected data requests.
    let user: User | undefined
    try {
      const authHeaders = new Headers()
      const token = request.cookies.get('auth_token')?.value
      if (token) authHeaders.set('Authorization', `Bearer ${token}`)
      const response = await fetch(`${getServerApiBaseUrl()}/api/v1/identity/me`, {
        headers: authHeaders, cache: 'no-store', signal: AbortSignal.timeout(10000),
      })
      if (response.status === 401) return NextResponse.redirect(new URL('/login', request.url))
      if (!response.ok) return denied('暂时无法验证页面权限，请稍后重试。', 503)
      const payload = await response.json() as { data?: User }
      user = payload.data
      if (!user) return denied('无法获取当前用户的页面权限。', 503)
    } catch {
      return denied('暂时无法验证页面权限，请稍后重试。', 503)
    }
    if (user.role !== 'admin' && user.page_permission_rollouts?.[currentModule.moduleCode] === 'enforced') {
      if (request.nextUrl.pathname.replace(/\/$/, '') === currentModule.path) {
        const visible = getAuthorizedPageMenus(user.module_codes, user.page_permissions, user.page_permission_rollouts)
          .find((item) => item.moduleCode === currentModule.moduleCode)
        const target = visible && firstPage(visible.children)
        return target ? NextResponse.redirect(new URL(target, request.url)) : denied('未获得本模块的任何页面访问权限。')
      }
      const key = getPageKeyByPath(request.nextUrl.pathname)
      const grant = user.page_permissions?.find((item) => item.page_key === key)
      if (!key || !grant?.permissions?.includes('access')) return denied('未获得当前菜单页面的访问权限。')
      if (!grant.permissions.includes('query')) return denied('可以访问此页面，但尚未获得查询数据权限。请联系管理员授权。')
    }
  }
  return NextResponse.next({ request: { headers: requestHeaders } })
}

export const config = {
  matcher: [
    '/api/v1/:path*',
    '/uploads/:path*',
    '/((?!_next/static|_next/image|favicon.ico).*)',
    {
      source: '/:path*',
      has: [{ type: 'query', key: 'auth_token' }],
    },
  ],
}
