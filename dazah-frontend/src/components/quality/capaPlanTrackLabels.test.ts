import { describe, expect, it } from 'vitest'
import {
  progressLabel,
  reminderLabel,
  progressMeta,
  reminderMeta,
  PROGRESS_OPTIONS,
  REMINDER_OPTIONS,
} from './capaPlanTrackLabels'

describe('capaPlanTrackLabels', () => {
  describe('progressLabel', () => {
    it('maps English enum values to Chinese', () => {
      expect(progressLabel('pending')).toBe('未开始')
      expect(progressLabel('in_progress')).toBe('正在进行')
      expect(progressLabel('completed')).toBe('已完成')
    })

    it('normalizes legacy Chinese aliases', () => {
      expect(progressLabel('待开始')).toBe('未开始')
      expect(progressLabel('未开始')).toBe('未开始')
      expect(progressLabel('进行中')).toBe('正在进行')
      expect(progressLabel('正在进行')).toBe('正在进行')
      expect(progressLabel('完成')).toBe('已完成')
      expect(progressLabel('已完成')).toBe('已完成')
    })

    it('passes through unknown values and empty input', () => {
      expect(progressLabel('未知状态')).toBe('未知状态')
      expect(progressLabel(null)).toBe('-')
      expect(progressLabel(undefined)).toBe('-')
      expect(progressLabel('')).toBe('-')
    })
  })

  describe('reminderLabel', () => {
    it('maps English enum values to Chinese', () => {
      expect(reminderLabel('pending')).toBe('待提醒')
      expect(reminderLabel('reminded')).toBe('已提醒')
      expect(reminderLabel('confirmed')).toBe('已确认')
    })

    it('normalizes legacy Chinese aliases', () => {
      expect(reminderLabel('待提醒')).toBe('待提醒')
      expect(reminderLabel('未提醒')).toBe('待提醒')
      expect(reminderLabel('已提醒')).toBe('已提醒')
      expect(reminderLabel('已确认')).toBe('已确认')
    })

    it('passes through unknown values and empty input', () => {
      expect(reminderLabel('其他')).toBe('其他')
      expect(reminderLabel(null)).toBe('-')
      expect(reminderLabel(undefined)).toBe('-')
    })
  })

  describe('progressMeta', () => {
    it('returns label with semantic color', () => {
      expect(progressMeta('completed')).toEqual({ label: '已完成', color: 'green' })
      expect(progressMeta('in_progress')).toEqual({ label: '正在进行', color: 'processing' })
      expect(progressMeta('pending')).toEqual({ label: '未开始', color: 'default' })
    })
  })

  describe('reminderMeta', () => {
    it('returns label with semantic color', () => {
      expect(reminderMeta('confirmed')).toEqual({ label: '已确认', color: 'green' })
      expect(reminderMeta('reminded')).toEqual({ label: '已提醒', color: 'gold' })
      expect(reminderMeta('pending')).toEqual({ label: '待提醒', color: 'default' })
    })
  })

  it('form options include enum values and legacy Chinese values', () => {
    const progressValues = PROGRESS_OPTIONS.map((o) => o.value)
    expect(progressValues).toContain('pending')
    expect(progressValues).toContain('完成')

    const reminderValues = REMINDER_OPTIONS.map((o) => o.value)
    expect(reminderValues).toContain('confirmed')
    expect(reminderValues).toContain('已确认')
  })
})
