import { describe, expect, it } from 'vitest'
import dayjs from 'dayjs'

import {
  toApiValue,
  toFormValue,
} from './inspectionFeishuFormFields'
import type { InspectionFeishuFieldMeta } from '@/types/quality'

const dateField: InspectionFeishuFieldMeta = {
  field_name: '维修时间',
  ui_type: 'DateTime',
  editable: true,
  options: null,
}

describe('toFormValue DateTime', () => {
  it('parses millisecond-timestamp strings (mirror cells) to the correct date', () => {
    // 回归：直接 dayjs("1765468800000") 会被日历正则误解析成 1771-10-14
    const value = toFormValue(dateField, '1765468800000') as dayjs.Dayjs
    expect(value.isValid()).toBe(true)
    // 时刻等价断言（避免 CI UTC 与本地时区格式化差异）
    expect(value.valueOf()).toBe(1765468800000)
  })

  it('parses numeric timestamps and ISO strings', () => {
    const fromNumber = toFormValue(dateField, 1765468800000) as dayjs.Dayjs
    expect(fromNumber.valueOf()).toBe(1765468800000)

    const fromIso = toFormValue(dateField, '2026-02-10') as dayjs.Dayjs
    expect(fromIso.format('YYYY-MM-DD')).toBe('2026-02-10')
  })

  it('round-trips through toApiValue as a writable date string', () => {
    const formValue = toFormValue(dateField, '1765468800000')
    const apiValue = toApiValue(dateField, formValue)
    expect(typeof apiValue).toBe('string')
    // 同本地时区下 round-trip 后日期保持一致
    const roundTripped = dayjs(apiValue as string, 'YYYY-MM-DD')
    expect(roundTripped.format('YYYY-MM-DD')).toBe(
      dayjs(1765468800000).format('YYYY-MM-DD'),
    )
  })
})