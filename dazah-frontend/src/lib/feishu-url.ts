/** 解析飞书多维表格 URL，提取 app_token 和 table_id */
export function parseFeishuBitableUrl(url: string): { app_token: string; table_id: string } | null {
  try {
    const parsed = new URL(url.trim())
    const baseMatch = parsed.pathname.match(/\/base\/([^/]+)/)
    if (!baseMatch) return null
    const app_token = baseMatch[1]
    const table_id = parsed.searchParams.get('table')
    if (!table_id) return null
    return { app_token, table_id }
  } catch {
    return null
  }
}

/** 解析飞书多维表格 Base 地址（可带或不带 table 参数），仅提取 app_token */
export function parseFeishuBaseUrl(url: string): string | null {
  try {
    const parsed = new URL(url.trim())
    const baseMatch = parsed.pathname.match(/\/base\/([^/]+)/)
    if (!baseMatch) return null
    return baseMatch[1]
  } catch {
    return null
  }
}
