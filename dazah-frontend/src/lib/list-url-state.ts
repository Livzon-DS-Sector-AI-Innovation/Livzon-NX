export type ListQueryPatch = Record<string, string | number | null | undefined>
export type ServerQueryRecord = Record<string, string | string[] | undefined>
const sensitiveQueryKey = /(?:^|[_-])(?:token|secret|password|authorization|cookie|session|api[_-]?key)(?:$|[_-])/i

export function firstQueryValue(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value
}

export function positiveListNumber(value: string | null | undefined, fallback: number, maximum = 1000): number {
  const parsed = Number(value)
  return Number.isSafeInteger(parsed) && parsed > 0 && parsed <= maximum ? parsed : fallback
}

export function readListPagination(query: ServerQueryRecord, defaultPageSize = 20) {
  return {
    page: positiveListNumber(firstQueryValue(query.page), 1),
    pageSize: positiveListNumber(firstQueryValue(query.page_size), defaultPageSize, 200),
  }
}

export function updateListUrl(
  pathname: string,
  current: URLSearchParams,
  patch: ListQueryPatch,
  resetPage = false,
): string {
  const next = new URLSearchParams(current)
  for (const key of [...next.keys()]) {
    if (key === 'returnTo' || sensitiveQueryKey.test(key)) next.delete(key)
  }
  if (resetPage) next.delete('page')
  for (const [key, value] of Object.entries(patch)) {
    if (key === 'returnTo' || sensitiveQueryKey.test(key)) continue
    if (value === null || value === undefined || value === '') next.delete(key)
    else next.set(key, String(value))
  }
  const query = next.toString()
  return `${pathname}${query ? `?${query}` : ''}`
}

export function detailHrefWithReturnTo(detailPath: string, listHref: string): string {
  if (!detailPath.startsWith('/') || detailPath.startsWith('//')) return detailPath
  const [pathname, queryString = ''] = detailPath.split('?')
  const query = new URLSearchParams(queryString)
  const [listPath, listQuery = ''] = listHref.split('?')
  const safeListQuery = new URLSearchParams(listQuery)
  for (const key of [...safeListQuery.keys()]) {
    if (key === 'returnTo' || sensitiveQueryKey.test(key)) safeListQuery.delete(key)
  }
  const safeQueryString = safeListQuery.toString()
  query.set('returnTo', `${listPath}${safeQueryString ? `?${safeQueryString}` : ''}`)
  return `${pathname}?${query}`
}

export function getSafeListReturnHref(returnTo: string | null, currentPath: string, expectedListPath?: string): string | undefined {
  if (!returnTo || !returnTo.startsWith('/') || returnTo.startsWith('//') || returnTo.includes('\\')) return undefined
  const [pathname] = returnTo.split('?')
  if ([...new URLSearchParams(returnTo.split('?')[1] || '').keys()].some((key) => sensitiveQueryKey.test(key))) return undefined
  return pathname !== '/' && (!expectedListPath || pathname === expectedListPath) && currentPath.startsWith(`${pathname}/`)
    ? returnTo
    : undefined
}
