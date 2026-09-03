import { NextRequest, NextResponse } from "next/server"

import { getPublicOrigin, isSecurePublicRequest } from "@/lib/public-origin"
import { getLocalLoginMode } from "@/lib/local-auth"
import { getBackendFallbackUrls } from "@/lib/server-api"

const AUTH_COOKIE_MAX_AGE = 60 * 60 * 24

function sanitizeNextPath(value: string | null): string {
  if (!value || !value.startsWith("/") || value.startsWith("//")) {
    return "/production"
  }
  if (value.startsWith("/api/") || value.startsWith("/auth/")) {
    return "/production"
  }
  return value
}

function loginRedirect(request: NextRequest, error: string) {
  const url = new URL("/login", getPublicOrigin(request))
  url.searchParams.set("error", error)
  return NextResponse.redirect(url, 303)
}

function tokenRedirectResponse(
  request: NextRequest,
  token: string,
  nextPath: string,
) {
  const completionPath = `/login/complete?next=${encodeURIComponent(nextPath)}`
  const targetUrl = new URL(completionPath, getPublicOrigin(request))
  const response = NextResponse.redirect(targetUrl, 303)
  response.cookies.set("auth_token", token, {
    httpOnly: true,
    maxAge: AUTH_COOKIE_MAX_AGE,
    path: "/",
    sameSite: "lax",
    secure: isSecurePublicRequest(request),
  })
  return response
}

export async function GET(request: NextRequest) {
  const token = request.nextUrl.searchParams.get("token")
  const nextPath = sanitizeNextPath(request.nextUrl.searchParams.get("next"))
  const publicOrigin = getPublicOrigin(request)

  if (!token) {
    return NextResponse.redirect(
      new URL("/login?error=missing_token", publicOrigin),
    )
  }

  return tokenRedirectResponse(request, token, nextPath)
}

export async function POST(request: NextRequest) {
  if (getLocalLoginMode() === "disabled") {
    return loginRedirect(request, "local_login_forbidden")
  }

  const formData = await request.formData()
  const username = String(formData.get("username") || "").trim()
  const password = String(formData.get("password") || "")
  const nextPath = sanitizeNextPath(String(formData.get("next") || ""))

  if (!username || !password) {
    return loginRedirect(request, "missing_credentials")
  }

  let lastError: unknown
  for (const backendUrl of getBackendFallbackUrls()) {
    try {
      const response = await fetch(
        `${backendUrl}/api/v1/identity/auth/local/login`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username, password }),
          cache: "no-store",
        },
      )
      const payload = await response.json().catch(() => null)

      if (!response.ok) {
        return loginRedirect(
          request,
          response.status === 403
            ? "local_login_forbidden"
            : "local_login_failed",
        )
      }

      const token = payload?.data?.access_token
      if (typeof token !== "string" || token.length === 0) {
        return loginRedirect(request, "missing_token")
      }

      return tokenRedirectResponse(request, token, nextPath)
    } catch (error) {
      lastError = error
    }
  }

  console.error("Local login callback error:", lastError)
  return loginRedirect(request, "local_login_failed")
}
