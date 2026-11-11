import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  SAFETY_COMMITMENT_PAGE_KEY,
  defaultEnterpriseStatus,
  formatCnDateTime,
  todayStr,
} from './safety-commitment'

afterEach(() => {
  vi.useRealTimers()
})

describe('safety-commitment lib', () => {
  it('页面键与菜单约定一致', () => {
    expect(SAFETY_COMMITMENT_PAGE_KEY).toBe('safety:safety-commitment')
  })

  it('todayStr 按北京时间取自然日（UTC 16:00 后已是次日）', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-11-09T16:30:00Z'))
    expect(todayStr()).toBe('2026-11-10')
    vi.setSystemTime(new Date('2026-11-09T15:59:00Z'))
    expect(todayStr()).toBe('2026-11-09')
  })

  it('formatCnDateTime 固定东八区，空值与非法值兜底', () => {
    expect(formatCnDateTime('2026-11-09T05:18:00+00:00')).toContain('13:18')
    expect(formatCnDateTime(null)).toBe('—')
    expect(formatCnDateTime('not-a-date')).toBe('—')
  })

  it('默认企业状态含 74 号文全部公告项', () => {
    const status = defaultEnterpriseStatus()
    expect(status.workshop_total).toBe(0)
    expect(status.special_work).toEqual({
      hot_work_level1: 0,
      hot_work_level2: 0,
      height_work: 0,
      confined_space: 0,
      other: 0,
    })
    expect(status.major_hazard_safe).toBeNull()
    expect(status.contractor_work).toBe(false)
  })
})
