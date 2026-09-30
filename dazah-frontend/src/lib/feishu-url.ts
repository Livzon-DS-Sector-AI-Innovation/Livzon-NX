/**
 * 解析飞书多维表格 URL。
 * - /base/ 链接直接取 app_token；
 * - /wiki/ 链接是知识库节点链接，其 token 不是 app_token，app_token 字段保留
 *   原始链接，由后端在保存/读取子表时解析为真正的 app_token。
 */
export interface ParsedFeishuBitableUrl {
  app_token: string
  table_id: string | null
  view_id: string | null
  is_wiki: boolean
}

export function parseFeishuBitableUrl(url: string): ParsedFeishuBitableUrl | null {
  try {
    const trimmed = url.trim()
    const parsed = new URL(trimmed)
    const tableId = parsed.searchParams.get('table')
    const viewId = parsed.searchParams.get('view')
    const baseMatch = parsed.pathname.match(/\/base\/([^/?#]+)/)
    if (baseMatch) {
      return { app_token: baseMatch[1], table_id: tableId, view_id: viewId, is_wiki: false }
    }
    const wikiMatch = parsed.pathname.match(/\/wiki\/([^/?#]+)/)
    if (wikiMatch) {
      return { app_token: trimmed, table_id: tableId, view_id: viewId, is_wiki: true }
    }
    return null
  } catch {
    return null
  }
}

/** 解析飞书多维表格 Base 地址（可带或不带 table 参数），提取 app_token 载体（wiki 链接返回原始链接） */
export function parseFeishuBaseUrl(url: string): string | null {
  return parseFeishuBitableUrl(url)?.app_token ?? null
}

/** 子表名归一化：全角转半角、忽略大小写与空白、括号等标点，保证「汉光（K1）」能匹配「汉光K1成品检验」 */
export function normalizeFeishuTableName(value: string): string {
  return value
    .toLowerCase()
    .replace(/[（）]/g, (ch) => (ch === '（' ? '(' : ')'))
    .replace(/[^0-9a-z\u4e00-\u9fa5]/g, '')
}

/** 按名称匹配子表：优先归一化后精确匹配，其次归一化后包含匹配 */
export function matchFeishuTableByName(
  names: Array<string | null | undefined>,
  tables: Array<{ table_id: string; table_name: string }>,
): { table_id: string; table_name: string } | undefined {
  const normalizedNames = names
    .filter(Boolean)
    .map((name) => normalizeFeishuTableName(name as string))
    .filter(Boolean)
  if (normalizedNames.length === 0) return undefined
  const exact = tables.find((t) =>
    normalizedNames.includes(normalizeFeishuTableName(t.table_name)),
  )
  if (exact) return exact
  return tables.find((t) => {
    const tableName = normalizeFeishuTableName(t.table_name)
    if (!tableName) return false
    return normalizedNames.some(
      (n) => tableName.includes(n) || n.includes(tableName),
    )
  })
}
