import type { NextRequest } from "next/server"

export function getPublicOrigin(request: NextRequest): string {
  const forwardedProto = request.headers
    .get("x-forwarded-proto")
    ?.split(",")[0]
    ?.trim()
  const forwardedHost = request.headers
    .get("x-forwarded-host")
    ?.split(",")[0]
    ?.trim()
  const host = forwardedHost || request.headers.get("host") || request.nextUrl.host
  const protocolFromUrl = request.nextUrl.protocol.replace(":", "")
  const proto =
    forwardedProto ||
    (host.startsWith("localhost") || host.startsWith("127.0.0.1")
      ? "http"
      : protocolFromUrl || "https")

  return `${proto}://${host}`
}

export function isSecurePublicRequest(request: NextRequest): boolean {
  return new URL(getPublicOrigin(request)).protocol === "https:"
}

/** Login forms must prove their browser source before receiving a session. */
export function isTrustedBrowserWriteRequest(request: NextRequest): boolean {
  if (request.headers.get("sec-fetch-site") === "cross-site") return false
  const expected = getPublicOrigin(request)
  const origin = request.headers.get("origin")
  if (origin) return origin === expected
  const referer = request.headers.get("referer")
  if (!referer) return false
  try {
    return new URL(referer).origin === expected
  } catch {
    return false
  }
}
