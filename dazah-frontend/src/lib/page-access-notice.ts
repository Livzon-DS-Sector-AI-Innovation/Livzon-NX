export const PAGE_ACCESS_NOTICE_SEGMENT = 'page-access-notice'
export const PAGE_ACCESS_NOTICE_PATH = `/${PAGE_ACCESS_NOTICE_SEGMENT}`
export const PAGE_ACCESS_NOTICE_HEADER = 'X-Dazah-Page-Access-Notice'
export const QUERY_PERMISSION_REQUIRED = 'query-required'
export const MENU_PAGE_UNAVAILABLE = 'menu-unavailable'
export const PAGE_NOT_FOUND = 'page-not-found'

export type PageAccessNoticeReason = typeof QUERY_PERMISSION_REQUIRED | typeof MENU_PAGE_UNAVAILABLE | typeof PAGE_NOT_FOUND
