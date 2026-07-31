import { describe, expect, it } from 'vitest'

import { getAuthCompletionPresentation } from './AuthCompletion'

describe('getAuthCompletionPresentation', () => {
  it.each([
    ['checking', '正在验证身份', '正在读取企业身份和访问权限，请稍候。'],
    ['ready', '身份验证成功', '企业身份和访问权限已确认。'],
    ['entering', '正在进入系统', '工作台准备完成，即将为你打开。'],
    ['error', '身份验证未完成', '请检查认证状态后重新登录。'],
  ] as const)(
    'provides clear user-facing copy for the %s state',
    (state, title, description) => {
      expect(getAuthCompletionPresentation(state)).toMatchObject({
        title,
        description,
      })
    },
  )
})
