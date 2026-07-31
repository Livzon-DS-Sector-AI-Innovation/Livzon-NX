import { describe, expect, it } from 'vitest'

import {
  countFilledResults,
  getAiFillErrorMessage,
  getTableColumnCount,
} from './AiFillPanel.logic'

describe('AI fill result helpers', () => {
  it('counts only successfully filled fields', () => {
    expect(
      countFilledResults([
        { status: 'filled' },
        { status: 'skipped' },
        { status: 'filled' },
      ]),
    ).toBe(2)
  })

  it('normalizes unknown errors and table dimensions', () => {
    expect(getAiFillErrorMessage('timeout', 'AI 提取失败')).toBe('AI 提取失败')
    expect(getAiFillErrorMessage(new Error('请求超时'), '失败')).toBe('请求超时')
    expect(getTableColumnCount([['项目', '标准'], ['性状', '白色粉末']])).toBe(2)
    expect(getTableColumnCount('not a table')).toBe(0)
  })
})
