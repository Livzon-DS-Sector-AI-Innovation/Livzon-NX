import { describe, expect, it } from 'vitest'

import { resolveFeishuUrlFill } from './HrFeishuSettingsPage'

describe('resolveFeishuUrlFill（HR 飞书设置网址填充）', () => {
  it('未粘贴网址时提示为空', () => {
    expect(resolveFeishuUrlFill('')).toEqual({ kind: 'empty' })
    expect(resolveFeishuUrlFill('   ')).toEqual({ kind: 'empty' })
  })

  it('非多维表格网址判定为无法识别', () => {
    expect(resolveFeishuUrlFill('https://example.com/not-a-base')).toEqual({
      kind: 'invalid',
    })
    expect(resolveFeishuUrlFill('不是网址')).toEqual({ kind: 'invalid' })
  })

  it('网址不含 table 参数时仅提取 App Token（子表可选）', () => {
    expect(
      resolveFeishuUrlFill('https://xxx.feishu.cn/base/bascn123'),
    ).toEqual({ kind: 'partial', app_token: 'bascn123' })
  })

  it('完整子表链接同时提取 App Token 与 Table ID', () => {
    expect(
      resolveFeishuUrlFill(
        'https://xxx.feishu.cn/base/bascn123?table=tbl456&view=view789',
      ),
    ).toEqual({
      kind: 'full',
      app_token: 'bascn123',
      base_table_id: 'tbl456',
    })
  })
})
