import { describe, expect, it } from 'vitest'
import { parseFeishuBaseUrl, parseFeishuBitableUrl } from './feishu-url'

describe('parseFeishuBitableUrl', () => {
  it('parses full bitable sub-table links with table and view params', () => {
    expect(
      parseFeishuBitableUrl(
        'https://j0eukrlohu.feishu.cn/base/EZUib0hvTa7Infsz9xScjFpAnvc?table=tblQeNmOWMCAaLrX&view=vewABCDEFG',
      ),
    ).toEqual({
      app_token: 'EZUib0hvTa7Infsz9xScjFpAnvc',
      table_id: 'tblQeNmOWMCAaLrX',
      view_id: 'vewABCDEFG',
    })
  })

  it('accepts shared base links without table param (regression: ?from=from_copylink)', () => {
    expect(
      parseFeishuBitableUrl(
        'https://j0eukrlohu.feishu.cn/base/EZUib0hvTa7lnfsz9xScjFpAnvc?from=from_copylink',
      ),
    ).toEqual({
      app_token: 'EZUib0hvTa7lnfsz9xScjFpAnvc',
      table_id: null,
      view_id: null,
    })
  })

  it('trims surrounding whitespace', () => {
    const parsed = parseFeishuBitableUrl(
      '  https://example.feishu.cn/base/app-token?table=tbl-1\t',
    )
    expect(parsed).toEqual({ app_token: 'app-token', table_id: 'tbl-1', view_id: null })
  })

  it('rejects non-base and malformed urls', () => {
    expect(parseFeishuBitableUrl('https://example.feishu.cn/wiki/AbCdEf?table=tbl-1')).toBeNull()
    expect(parseFeishuBitableUrl('https://example.com/no-base')).toBeNull()
    expect(parseFeishuBitableUrl('not-a-url')).toBeNull()
    expect(parseFeishuBitableUrl('')).toBeNull()
  })
})

describe('parseFeishuBaseUrl', () => {
  it('extracts app token with or without table param', () => {
    expect(parseFeishuBaseUrl('https://example.feishu.cn/base/app-token')).toBe('app-token')
    expect(parseFeishuBaseUrl('https://example.feishu.cn/base/app-token?table=tbl-1')).toBe('app-token')
    expect(parseFeishuBaseUrl('https://example.com/no-base')).toBeNull()
  })
})
