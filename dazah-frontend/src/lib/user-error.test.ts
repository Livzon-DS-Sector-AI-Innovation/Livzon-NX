import { describe, expect, it } from 'vitest'
import { getUserErrorMessage } from './user-error'

describe('getUserErrorMessage', () => {
  it('preserves a Chinese business error', () => {
    expect(getUserErrorMessage(new Error('库存不足，请调整数量'), undefined, 400))
      .toBe('库存不足，请调整数量')
  })

  it.each([
    [new Error('Failed to fetch'), undefined, '网络连接失败，请检查网络后重试'],
    [new Error('The operation was aborted'), undefined, '请求超时，请稍后重试'],
    ['Forbidden', 403, '没有执行此操作的权限，请联系管理员'],
    ['Internal Server Error', 500, '服务暂时不可用，请稍后重试'],
    [new Error('Unknown provider failure'), undefined, '操作未完成，请稍后重试'],
  ])('converts raw errors into actionable Chinese text', (error, status, expected) => {
    expect(getUserErrorMessage(error, undefined, status)).toBe(expected)
  })
})
