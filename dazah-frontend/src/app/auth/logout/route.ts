import { NextRequest, NextResponse } from "next/server"

import { getPublicOrigin } from "@/lib/public-origin"

export async function GET(request: NextRequest) {
  const response = NextResponse.redirect(
    new URL("/login", getPublicOrigin(request)),
  )
  response.cookies.set("auth_token", "", {
    path: "/",
    maxAge: 0,
  })
  return response
}
