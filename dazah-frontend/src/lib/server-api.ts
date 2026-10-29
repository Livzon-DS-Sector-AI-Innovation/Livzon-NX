import { apiV1 } from "@/lib/api-path"

const DEFAULT_SERVER_API_BASE_URL = "http://localhost:8000"
export function getServerApiBaseUrl(): string {
  const configured = process.env.API_BASE_URL?.trim()
  if (!configured && process.env.NODE_ENV === "production") {
    throw new Error("API_BASE_URL must be configured in production")
  }
  return (configured || DEFAULT_SERVER_API_BASE_URL).replace(/\/+$/, "")
}

export function serverApiUrl(path: string): string {
  return `${getServerApiBaseUrl()}${apiV1(path)}`
}

export function getBackendFallbackUrls(): string[] {
  // Keep the existing caller contract, but never replay credentials to other hosts.
  return [getServerApiBaseUrl()]
}
