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
