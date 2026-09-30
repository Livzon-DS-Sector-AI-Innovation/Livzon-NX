import { afterEach, describe, expect, it, vi } from 'vitest'
import { getOffboardingEmploymentStatus } from './offboardingStatus'

describe('offboarding employment status', () => {
  afterEach(() => vi.useRealTimers())

  it.each([
    ['2026-09-29', '2026-09-30', '离职'],
    ['2026-09-30', '2026-09-30', '在职'],
    ['2026-10-01', '2026-09-30', '在职'],
    ['2025-12-31', '2026-01-01', '离职'],
    ['2028-02-29', '2028-03-01', '离职'],
  ])('compares calendar dates (%s, %s)', (lastDay, today, status) => {
    expect(getOffboardingEmploymentStatus(lastDay, today)).toBe(status)
  })

  it.each([undefined, '', 'invalid', '2026-02-30', '2026-13-01', '2026-9-30'])('does not infer a status for invalid date %s', lastDay => {
    expect(getOffboardingEmploymentStatus(lastDay, '2026-09-30')).toBeNull()
  })

  it('keeps the employee active throughout the last working day and switches after midnight', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 8, 30, 23, 59, 59))
    expect(getOffboardingEmploymentStatus('2026-09-30')).toBe('在职')
    vi.setSystemTime(new Date(2026, 9, 1, 0, 0, 0))
    expect(getOffboardingEmploymentStatus('2026-09-30')).toBe('离职')
  })
})
