const filterKeys = new Set([
  "keyword", "status", "page", "page_size", "date_from", "date_to",
  "department_id", "product_id", "year", "month",
])

/** Send location hints only. The backend resolves names and current grants. */
export function buildAgentPageHint(location: Pick<Location, "pathname" | "search">) {
  const filters: Record<string, string> = {}
  for (const [key, value] of new URLSearchParams(location.search)) {
    if (filterKeys.has(key) && value.length <= 200) filters[key] = value
  }
  return { route_path: location.pathname, filters }
}
