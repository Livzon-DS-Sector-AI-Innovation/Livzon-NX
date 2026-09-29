import { describe, expect, it } from 'vitest'
import {
  matchFeishuTableByName,
  parseFeishuBaseUrl,
  parseFeishuBitableUrl,
} from './feishu-url'

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
      is_wiki: false,
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
      is_wiki: false,
    })
  })

  it('trims surrounding whitespace', () => {
    const parsed = parseFeishuBitableUrl(
      '  https://example.feishu.cn/base/app-token?table=tbl-1\t',
    )
    expect(parsed).toEqual({ app_token: 'app-token', table_id: 'tbl-1', view_id: null, is_wiki: false })
  })

  it('recognizes wiki links and keeps the raw url plus table/view params for backend resolution', () => {
    const wikiUrl =
      'https://j0eukrlohu.feishu.cn/wiki/TeBUwZkJEiOPK2kKLxxcZ1SCnWg?table=tblivbUvnYDjATiL&view=vewABC&from=from_copylink'
    expect(parseFeishuBitableUrl(wikiUrl)).toEqual({
      app_token: wikiUrl,
      table_id: 'tblivbUvnYDjATiL',
      view_id: 'vewABC',
      is_wiki: true,
    })
    expect(parseFeishuBitableUrl('https://example.feishu.cn/wiki/WikiToken123')).toEqual({
      app_token: 'https://example.feishu.cn/wiki/WikiToken123',
      table_id: null,
      view_id: null,
      is_wiki: true,
    })
  })

  it('rejects bare tokens, non-base and malformed urls', () => {
    expect(parseFeishuBitableUrl('TeBUwZkJEiOPK2kKLxxcZ1SCnWg')).toBeNull()
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

  it('keeps the raw wiki url so the backend can resolve the node token', () => {
    const wikiUrl = 'https://example.feishu.cn/wiki/WikiToken123?table=tbl-1'
    expect(parseFeishuBaseUrl(wikiUrl)).toBe(wikiUrl)
  })
})

describe('matchFeishuTableByName（按名称匹配子表）', () => {
  const tables = [
    { table_id: 'blk1', table_name: '原辅料进出台账' },
    { table_id: 'blk2', table_name: '包材进出台账-26年' },
    { table_id: 'blk3', table_name: '试剂台账' },
  ]

  it('精确与归一化匹配（页面名含空格/全角差异也能对上）', () => {
    expect(matchFeishuTableByName(['原辅料进出台账'], tables)?.table_id).toBe('blk1')
    expect(matchFeishuTableByName(['包材进出台账（26年）'], tables)?.table_id).toBe('blk2')
  })

  it('无匹配或名称为空时返回 undefined', () => {
    expect(matchFeishuTableByName(['完全无关'], tables)).toBeUndefined()
    expect(matchFeishuTableByName([null, ''], tables)).toBeUndefined()
  })
})
