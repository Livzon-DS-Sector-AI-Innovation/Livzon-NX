import { ConfigProvider, theme } from 'antd'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { ActionRequestError } from '@/lib/server-action-result'
import { EquipmentQueryFailure, isEquipmentQueryAccessError } from './EquipmentQueryFailure'

describe.each([
  { name: '浅色', algorithm: theme.defaultAlgorithm },
  { name: '深色', algorithm: theme.darkAlgorithm },
])('$name 查询失败状态', ({ algorithm }) => {
  it.each([401, 403] as const)('HTTP %i 保留明确状态和恢复入口', status => {
    const html = renderToStaticMarkup(
      <ConfigProvider theme={{ algorithm }}>
        <EquipmentQueryFailure status={status} />
      </ConfigProvider>,
    )
    expect(html).toContain(status === 401 ? '登录已失效，请重新登录' : '没有执行此操作的权限，请联系管理员')
    expect(html).toContain(status === 401 ? 'href="/login"' : 'href="/"')
    expect(html).toContain(status === 401 ? '重新登录' : '返回平台')
  })
})

it('仅识别明确分类的 401/403，保留其他错误原有处理', () => {
  expect(isEquipmentQueryAccessError(new ActionRequestError(401, 'expired'))).toBe(true)
  expect(isEquipmentQueryAccessError(new ActionRequestError(403, 'denied'))).toBe(true)
  expect(isEquipmentQueryAccessError(new ActionRequestError(500, 'failed'))).toBe(false)
  expect(isEquipmentQueryAccessError({ status: 403 })).toBe(false)
  expect(isEquipmentQueryAccessError(new Error('403'))).toBe(false)
})
