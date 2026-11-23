import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

import { getServerApiBaseUrl } from '@/lib/server-api'
import { getModuleByKey, getPageKeyByPath, getAuthorizedPageMenus, getAuthorizedDirectoryEntryPath, expandEquipmentPagePermissions } from '@/lib/menu-config'
import type { SubMenuItem } from '@/lib/menu-config'
import { EQUIPMENT_CONSOLE_MODULE_HEADER, getQueryableEquipmentTabs, isEquipmentModule } from '@/lib/equipment-page-permissions'
import type { User } from '@/types/user'
import { isSystemAdministrator, isSystemSettingsPath } from '@/lib/administrator-role'
import { getEffectiveToken, IMPERSONATION_COOKIE, IMPERSONATION_RECOVERY_PATH } from '@/lib/impersonation'
import { MENU_PAGE_UNAVAILABLE, PAGE_ACCESS_NOTICE_HEADER, PAGE_ACCESS_NOTICE_PATH, PAGE_NOT_FOUND, QUERY_PERMISSION_REQUIRED } from '@/lib/page-access-notice'

function firstPage(items: SubMenuItem[]): string | undefined {
  for (const item of items) {
    if (item.path && !item.disabled) return item.path
    const nested = item.children && firstPage(item.children)
    if (nested) return nested
  }
}

function hasMenuPath(items: SubMenuItem[], pathname: string, includeDisabled = false): boolean {
  for (const item of items) {
    if (item.disabled && !includeDisabled) continue
    if (item.path.split('?')[0] === pathname) return true
    if (item.children && hasMenuPath(item.children, pathname, includeDisabled)) return true
  }
  return false
}

function denied(message: string, status = 403) {
  return new NextResponse(`<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>页面访问受限</title><body><main><h1>页面访问受限</h1><p>${message}</p><a href="/">返回平台</a></main></body></html>`, {
    status, headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' },
  })
}

function requireQueryPermission(request: NextRequest, requestHeaders: Headers) {
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    return denied('可以访问此页面，但尚未获得查询数据权限。请联系管理员授权。')
  }

  // The beforeFiles rewrite consumes this marker before the App Router selects a page.
  requestHeaders.set(PAGE_ACCESS_NOTICE_HEADER, QUERY_PERMISSION_REQUIRED)
  return NextResponse.next({
    request: { headers: requestHeaders },
    headers: { 'Cache-Control': 'private, no-store' },
  })
}

export async function proxy(request: NextRequest) {
  if (request.nextUrl.searchParams.has('auth_token')) {
    const target = request.nextUrl.clone()
    target.searchParams.delete('auth_token')
    return NextResponse.redirect(target)
  }

  const requestHeaders = new Headers(request.headers)
  requestHeaders.delete(PAGE_ACCESS_NOTICE_HEADER)
  const { pathname } = request.nextUrl
  if (pathname === PAGE_ACCESS_NOTICE_PATH || pathname.startsWith(`${PAGE_ACCESS_NOTICE_PATH}/`)) {
    return new NextResponse(null, { status: 404, headers: { 'Cache-Control': 'no-store' } })
  }

  if (
    request.nextUrl.pathname.startsWith('/api/v1/') ||
    request.nextUrl.pathname.startsWith('/uploads/')
  ) {
    const target = new URL(request.nextUrl.pathname, getServerApiBaseUrl())
    target.search = request.nextUrl.search

    const token = getEffectiveToken(request.cookies)
    if (token && (request.cookies.get(IMPERSONATION_COOKIE) || !requestHeaders.has('Authorization'))) {
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

  requestHeaders.set('X-Dazah-Page-Path', request.nextUrl.pathname)
  requestHeaders.delete(EQUIPMENT_CONSOLE_MODULE_HEADER)
  const consoleModule = request.nextUrl.pathname === '/equipment'
    ? request.nextUrl.searchParams.get('module')
    : null
  const hasConsoleModule = isEquipmentModule(consoleModule)
  if (hasConsoleModule) requestHeaders.set(EQUIPMENT_CONSOLE_MODULE_HEADER, consoleModule)
  const simulation = request.cookies.get(IMPERSONATION_COOKIE)
  const recovery = new URL(IMPERSONATION_RECOVERY_PATH, request.url)
  const safeNavigation = request.method === 'GET' || request.method === 'HEAD'
  if (simulation && safeNavigation && (
    request.nextUrl.pathname === '/login' || request.nextUrl.pathname.startsWith('/login/')
  )) return NextResponse.redirect(recovery)
  const currentModule = getModuleByKey(request.nextUrl.pathname.split('/')[1])
  if (currentModule || isSystemSettingsPath(request.nextUrl.pathname)
    || (simulation && ['/', '/no-access'].includes(request.nextUrl.pathname))) {
    // This gate runs before the App Router evaluates any child Server Component.
    // Layout-only guards can render concurrently with protected data requests.
    const login = new URL('/login', request.url)
    login.searchParams.set('next', request.nextUrl.pathname + request.nextUrl.search)
    const token = getEffectiveToken(request.cookies)
    if (!token) {
      if (simulation && !safeNavigation) return denied('模拟登录已失效，请返回管理员身份。', 401)
      return NextResponse.redirect(simulation ? recovery : login)
    }

    let user: User | undefined
    try {
      const response = await fetch(`${getServerApiBaseUrl()}/api/v1/identity/me`, {
        headers: { Authorization: `Bearer ${token}` },
        cache: 'no-store',
        signal: AbortSignal.timeout(10000),
      })
      if (response.status === 401) {
        if (simulation) {
          return safeNavigation
            ? NextResponse.redirect(recovery)
            : denied('模拟登录已失效，请返回管理员身份。', 401)
        }
        return NextResponse.redirect(login)
      }
      if (response.status === 503 && simulation && safeNavigation) return NextResponse.redirect(recovery)
      if (!response.ok) return denied('暂时无法验证页面权限，请稍后重试。', 503)
      const payload = await response.json() as { data?: User }
      user = payload.data
      if (!user) return denied('无法获取当前用户的页面权限。', 503)
    } catch {
      if (simulation && safeNavigation) return NextResponse.redirect(recovery)
      return denied('暂时无法验证页面权限，请稍后重试。', 503)
    }
    if (isSystemSettingsPath(request.nextUrl.pathname)) {
      return isSystemAdministrator(user)
        ? NextResponse.next({ request: { headers: requestHeaders } })
        : denied('仅系统管理员可以进入系统设置。')
    }
    if (!currentModule) return NextResponse.next({ request: { headers: requestHeaders } })
    if (safeNavigation) {
      // The fallback rewrite only applies when Next.js cannot resolve the URL.
      const isMenuPath = hasMenuPath(currentModule.children, pathname.replace(/\/$/, ''), true)
      requestHeaders.set(PAGE_ACCESS_NOTICE_HEADER, isMenuPath ? MENU_PAGE_UNAVAILABLE : PAGE_NOT_FOUND)
    }
    if (user.role !== 'admin') {
      const moduleLanding = !hasConsoleModule && request.nextUrl.pathname.replace(/\/$/, '') === currentModule.path
      if (moduleLanding) {
        const visible = getAuthorizedPageMenus(user.module_codes, user.page_permissions)
          .find((item) => item.moduleCode === currentModule.moduleCode)
        if (!visible || !hasMenuPath(visible.children, currentModule.path)) {
          const target = safeNavigation && visible && firstPage(visible.children)
          return target ? NextResponse.redirect(new URL(target, request.url)) : denied('未获得本模块的任何页面访问权限。')
        }
        if (currentModule.path === '/equipment') {
          return getQueryableEquipmentTabs(user).length
            ? NextResponse.next({ request: { headers: requestHeaders } })
            : requireQueryPermission(request, requestHeaders)
        }
      }
      // Navigation fallback must never replay a Server Action onto another page.
      if (safeNavigation && !moduleLanding) {
        const entry = getAuthorizedDirectoryEntryPath(request.nextUrl.pathname, user.page_permissions)
        if (entry && entry !== request.nextUrl.pathname.replace(/\/$/, '')) {
          return NextResponse.redirect(new URL(entry, request.url))
        }
      }
      const key = getPageKeyByPath(
        hasConsoleModule ? `/equipment/${consoleModule}` : request.nextUrl.pathname,
      )
      // 展开旧「车间×功能」叶授权后再查找，避免投影授权被误拒
      const grant = expandEquipmentPagePermissions(user.page_permissions)
        .find((item) => item.page_key === key)
      if (!key || !grant?.permissions?.includes('access')) return denied('未获得当前菜单页面的访问权限。')
      if (!grant.permissions.includes('query')) return requireQueryPermission(request, requestHeaders)
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
