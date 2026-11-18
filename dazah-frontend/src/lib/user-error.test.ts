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

  it.each([
    '导入失败：Minified React error #441',
    '无法保存：An unexpected response was received from the server.',
    '加载失败：ChunkLoadError: Loading chunk 18 failed',
    '读取失败：TypeError: 数据对象为空',
    '异常\n    at internalPath (C:/internal/service.ts:2:2)',
    '请求失败 Authorization: Bearer synthetic',
  ])('replaces framework and infrastructure details in legacy feedback', message => {
    expect(getUserErrorMessage(message, '请重新打开页面')).toBe('请重新打开页面')
  })

  it('never displays unknown Chinese 5xx diagnostics', () => {
    expect(getUserErrorMessage('内部数据库异常和调试详情', undefined, 503))
      .toBe('服务暂时不可用，请稍后重试')
  })
})
