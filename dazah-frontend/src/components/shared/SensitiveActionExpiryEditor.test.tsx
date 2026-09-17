import { describe, expect, it, vi } from 'vitest'
import dayjs from 'dayjs'
import { sensitiveActionExpiryFromDays } from './SensitiveActionExpiryEditor'

describe('sensitive action expiry presets', () => {
  it('creates a future end-of-day expiry', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-09-16T02:00:00.000Z'))
    const expiry = sensitiveActionExpiryFromDays(30)
    expect(dayjs(expiry).isAfter(dayjs())).toBe(true)
    expect(dayjs(expiry).diff(dayjs(), 'day')).toBeGreaterThanOrEqual(30)
    vi.useRealTimers()
  })
})
