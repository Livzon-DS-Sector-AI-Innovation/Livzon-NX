'use client'

import { usePathname, useRouter, useSearchParams } from 'next/navigation'
import { detailHrefWithReturnTo, positiveListNumber, updateListUrl, type ListQueryPatch } from './list-url-state'

export function useListUrlState(defaultPageSize = 20) {
  const pathname = usePathname()
  const router = useRouter()
  const searchParams = useSearchParams()
  const queryString = searchParams.toString()
  const params = new URLSearchParams(queryString)
  const page = positiveListNumber(params.get('page'), 1)
  const pageSize = positiveListNumber(params.get('page_size'), defaultPageSize, 200)
  const href = `${pathname}${queryString ? `?${queryString}` : ''}`

  const setListQuery = (patch: ListQueryPatch, resetPage = false) => {
    router.replace(updateListUrl(pathname, params, patch, resetPage), { scroll: false })
  }

  const detailHref = (detailPath: string) => detailHrefWithReturnTo(detailPath, href)

  return { page, pageSize, params, href, setListQuery, detailHref }
}
