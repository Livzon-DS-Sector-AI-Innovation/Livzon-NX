import { NextRequest, NextResponse } from "next/server"

import { getPublicOrigin } from "@/lib/public-origin"

function sanitizeNextPath(value: string | null): string {
  if (!value || !value.startsWith("/") || value.startsWith("//")) {
    return "/production"
  }
  if (value.startsWith("/api/") || value.startsWith("/auth/")) {
    return "/production"
  }
  return value
}

export async function GET(request: NextRequest) {
  const nextPath = sanitizeNextPath(request.nextUrl.searchParams.get("next"))
  const url = new URL("/api/v1/identity/auth/login", getPublicOrigin(request))
  url.searchParams.set("next", nextPath)
  return NextResponse.redirect(url)
}
