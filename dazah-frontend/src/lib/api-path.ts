const API_PREFIX = "/api/v1"

export function apiV1(path: string): string {
  if (path === "") {
    return API_PREFIX
  }
  const normalizedPath = path.startsWith("/") ? path : `/${path}`
  if (normalizedPath === API_PREFIX || normalizedPath.startsWith(`${API_PREFIX}/`)) {
    return normalizedPath
  }
  return `${API_PREFIX}${normalizedPath}`
}

export function backendAssetPath(path: string): string {
  if (path.startsWith("http")) {
    return path
  }
  return `/${path.replace(/^\/+/, "")}`
}
