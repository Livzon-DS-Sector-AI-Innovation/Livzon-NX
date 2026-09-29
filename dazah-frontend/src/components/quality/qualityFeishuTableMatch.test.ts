import { describe, expect, it } from 'vitest'

import type { QualityFeishuEntitySettingItem } from '@/types/quality'
import { normalizeFeishuTableName } from '@/lib/feishu-url'
import { matchTableForEntity } from './QualityFeishuSettingsPage'

function buildEntity(overrides: Partial<QualityFeishuEntitySettingItem>) {
  return {
    entity_code: 'entity_x',
    entity_name: '',
    entity_group: '',
    app_token: null,
    base_table_name: null,
    base_table_id: null,
    feishu_form_url: null,
    is_enabled: false,
    enable_push_to_feishu: false,
    enable_pull_from_feishu: false,
    field_mappings: [],
    sort_order: 0,
    ...overrides,
  } as QualityFeishuEntitySettingItem
}

describe('normalizeFeishuTableName（子表名归一化）', () => {
  it('忽略大小写、空白、全角/半角括号等标点差异', () => {
    expect(normalizeFeishuTableName('汉光（K1）')).toBe('汉光k1')
    expect(normalizeFeishuTableName('汉光K1')).toBe('汉光k1')
    expect(normalizeFeishuTableName(' 2025年 异常报告 ')).toBe('2025年异常报告')
    expect(normalizeFeishuTableName('L-苯丙氨酸')).toBe('l苯丙氨酸')
  })
})

describe('matchTableForEntity（按名称匹配子表）', () => {
  const tables = [
    { table_id: 'tbl1', table_name: '汉光（K1）成品检验' },
    { table_id: 'tbl2', table_name: '维多-K2 成品检验' },
    { table_id: 'tbl3', table_name: '2025年异常报告' },
    { table_id: 'tbl4', table_name: 'TAPI-K5' },
  ]

  it('实体名与子表名完全一致时精确匹配', () => {
    const entity = buildEntity({ entity_name: 'TAPI-K5' })
    expect(matchTableForEntity(entity, tables)?.table_id).toBe('tbl4')
  })

  it('全角括号与连字符等标点差异不影响匹配', () => {
    const entity = buildEntity({ entity_name: '汉光（K1）' })
    expect(matchTableForEntity(entity, tables)?.table_id).toBe('tbl1')
  })

  it('实体名是子表名的一部分时按包含匹配', () => {
    const entity = buildEntity({ entity_name: '维多（K2）' })
    expect(matchTableForEntity(entity, tables)?.table_id).toBe('tbl2')
  })

  it('已配置的表名也参与匹配（按年分表实体）', () => {
    const entity = buildEntity({
      entity_name: '成品异常报告-2025年',
      base_table_name: '2025年',
    })
    expect(matchTableForEntity(entity, tables)?.table_id).toBe('tbl3')
  })

  it('没有任何子表能匹配时返回 undefined', () => {
    const entity = buildEntity({ entity_name: '完全不相关的实体' })
    expect(matchTableForEntity(entity, tables)).toBeUndefined()
  })

  it('归一化后为空的子表名不会误匹配任何实体', () => {
    const entity = buildEntity({ entity_name: '汉光（K1）' })
    const symbolOnlyTables = [{ table_id: 'tblX', table_name: '——' }]
    expect(matchTableForEntity(entity, symbolOnlyTables)).toBeUndefined()
  })
})
