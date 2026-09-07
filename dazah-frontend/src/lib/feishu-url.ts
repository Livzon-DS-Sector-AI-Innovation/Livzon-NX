/** 解析飞书多维表格 URL：有 /base/<app_token> 即识别成功；table/view 参数可选 */
export interface ParsedFeishuBitableUrl {
  app_token: string
  table_id: string | null
  view_id: string | null
}

export function parseFeishuBitableUrl(url: string): ParsedFeishuBitableUrl | null {
  try {
    const parsed = new URL(url.trim())
    const baseMatch = parsed.pathname.match(/\/base\/([^/]+)/)
    if (!baseMatch) return null
    return {
      app_token: baseMatch[1],
      table_id: parsed.searchParams.get('table'),
      view_id: parsed.searchParams.get('view'),
    }
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
