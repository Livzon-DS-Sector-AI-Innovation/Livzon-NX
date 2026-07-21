import { NextRequest, NextResponse } from 'next/server'

import { getBackendFallbackUrls } from '@/lib/server-api'

export async function GET(request: NextRequest) {
  return proxyRequest(request)
}

export async function POST(request: NextRequest) {
  return proxyRequest(request)
}

export async function PUT(request: NextRequest) {
  return proxyRequest(request)
}

export async function DELETE(request: NextRequest) {
  return proxyRequest(request)
}

export async function PATCH(request: NextRequest) {
  return proxyRequest(request)
}

async function proxyRequest(request: NextRequest) {
  const pathname = request.nextUrl.pathname
  const searchParams = request.nextUrl.searchParams.toString()
  const backendPath = `${pathname}${searchParams ? `?${searchParams}` : ''}`
  const body =
    request.method !== 'GET' && request.method !== 'HEAD'
      ? await request.arrayBuffer()
      : undefined

  const fetchOptions: RequestInit = {
    method: request.method,
    headers: request.headers,
    body,
    redirect: 'follow',
  }

  let lastError: unknown
  for (const backendUrl of getBackendFallbackUrls()) {
    const url = `${backendUrl}${backendPath}`

    try {
      const response = await fetch(url, fetchOptions)

      // If backend returned a redirect, redirect browser to the same location
      if (response.redirected) {
        return NextResponse.redirect(response.url)
      }

      if (response.headers.get('content-type')?.includes('text/event-stream')) {
        return new NextResponse(response.body, {
          status: response.status,
          statusText: response.statusText,
          headers: {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            Connection: 'keep-alive',
          },
        })
      }

      const contentType = response.headers.get('content-type') || ''
      if (!contentType.includes('application/json')) {
        const headers = new Headers()
        const forwardedHeaders = [
          'content-type',
          'content-disposition',
          'content-length',
          'cache-control',
        ]
        forwardedHeaders.forEach((headerName) => {
          const value = response.headers.get(headerName)
          if (value) headers.set(headerName, value)
        })

        return new NextResponse(response.body, {
          status: response.status,
          statusText: response.statusText,
          headers,
        })
      }

      const data = await response.json()
      const nextResponse = NextResponse.json(data, {
        status: response.status,
        statusText: response.statusText,
      })
      if (
        response.ok &&
        request.method === 'POST' &&
        pathname === '/api/v1/identity/auth/local/login'
      ) {
        const token = data?.data?.access_token
        if (typeof token === 'string' && token.length > 0) {
          nextResponse.cookies.set('auth_token', token, {
            httpOnly: true,
            maxAge: 60 * 60 * 24 * 7,
            path: '/',
            sameSite: 'lax',
            secure: request.nextUrl.protocol === 'https:',
          })
        }
      }
      return nextResponse
    } catch (error) {
      lastError = error
    }
  }

  console.error('Proxy error:', lastError)
  return NextResponse.json({ error: 'Proxy error' }, { status: 500 })
}
