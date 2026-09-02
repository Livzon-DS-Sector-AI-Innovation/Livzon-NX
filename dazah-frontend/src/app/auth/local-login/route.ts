import { NextRequest, NextResponse } from "next/server"

import { getPublicOrigin, isSecurePublicRequest } from "@/lib/public-origin"
import { getLocalLoginMode } from "@/lib/local-auth"
import { getBackendFallbackUrls } from "@/lib/server-api"

const AUTH_COOKIE_MAX_AGE = 60 * 60 * 24

function sanitizeNextPath(value: FormDataEntryValue | null): string {
  const raw = typeof value === "string" ? value : ""
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) {
    return "/production"
  }
  if (raw.startsWith("/api/") || raw.startsWith("/auth/")) {
    return "/production"
  }
  return raw
}

function loginRedirect(request: NextRequest, error: string) {
  const url = new URL("/login", getPublicOrigin(request))
  url.searchParams.set("error", error)
  return NextResponse.redirect(url, 303)
}

export async function POST(request: NextRequest) {
  if (getLocalLoginMode() === "disabled") {
    return loginRedirect(request, "local_login_forbidden")
  }

  const formData = await request.formData()
  const username = String(formData.get("username") || "").trim()
  const password = String(formData.get("password") || "")
  const nextPath = sanitizeNextPath(formData.get("next"))

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

      const completionPath = `/login/complete?next=${encodeURIComponent(nextPath)}`
      const redirectUrl = new URL(completionPath, getPublicOrigin(request))
      const redirectResponse = NextResponse.redirect(redirectUrl, 303)
      redirectResponse.cookies.set("auth_token", token, {
        httpOnly: true,
        maxAge: AUTH_COOKIE_MAX_AGE,
        path: "/",
        sameSite: "lax",
        secure: isSecurePublicRequest(request),
      })
      return redirectResponse
    } catch (error) {
      lastError = error
    }
  }

  console.error("Local login proxy error:", lastError)
  return loginRedirect(request, "local_login_failed")
}
