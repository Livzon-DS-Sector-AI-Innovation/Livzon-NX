import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

import { getServerApiBaseUrl } from '@/lib/server-api'

const AUTH_COOKIE_MAX_AGE = 60 * 60 * 24

export function proxy(request: NextRequest) {
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
      secure: request.nextUrl.protocol === 'https:',
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

    return NextResponse.rewrite(target, {
      request: {
        headers: requestHeaders,
      },
    })
  }

  return NextResponse.next()
}

export const config = {
  matcher: [
    '/api/v1/:path*',
    '/uploads/:path*',
    {
      source: '/:path*',
      has: [{ type: 'query', key: 'auth_token' }],
    },
  ],
}
