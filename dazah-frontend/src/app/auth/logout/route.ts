import { NextRequest, NextResponse } from "next/server"

import { getPublicOrigin } from "@/lib/public-origin"
import { getBackendFallbackUrls } from "@/lib/server-api"

export async function GET(request: NextRequest) {
  const token = request.cookies.get("auth_token")?.value
  if (token) {
    let revoked = false
    for (const backendUrl of getBackendFallbackUrls()) {
      try {
        const result = await fetch(`${backendUrl}/api/v1/identity/auth/session/logout`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          cache: "no-store",
        })
        revoked = result.ok || result.status === 401
        break
      } catch {
        // Try the next configured backend endpoint.
      }
    }
    if (!revoked) {
      return new NextResponse("退出登录暂时失败，请稍后重试", {
        status: 503,
        headers: { "Cache-Control": "no-store" },
      })
    }
  }
  const response = NextResponse.redirect(
    new URL("/login", getPublicOrigin(request)),
  )
  response.cookies.set("auth_token", "", {
    path: "/",
    maxAge: 0,
  })
  response.headers.set("Cache-Control", "no-store")
  return response
}
