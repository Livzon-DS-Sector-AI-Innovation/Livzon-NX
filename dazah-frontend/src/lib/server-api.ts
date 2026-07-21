import { apiV1 } from "@/lib/api-path"

const DEFAULT_SERVER_API_BASE_URL = "http://localhost:8000"
const LOCAL_BACKEND_FALLBACK_URLS = [
  "http://app:8000",
  "http://backend:8000",
  "http://dazah-backend:8000",
  "http://dazah-backend-app:8000",
  "http://localhost:8000",
  "http://127.0.0.1:8000",
  "http://host.docker.internal:8000",
]

export function getServerApiBaseUrl(): string {
  return (process.env.API_BASE_URL || DEFAULT_SERVER_API_BASE_URL).replace(/\/+$/, "")
}

export function serverApiUrl(path: string): string {
  return `${getServerApiBaseUrl()}${apiV1(path)}`
}

export function getBackendFallbackUrls(): string[] {
  return Array.from(new Set([getServerApiBaseUrl(), ...LOCAL_BACKEND_FALLBACK_URLS]))
}
