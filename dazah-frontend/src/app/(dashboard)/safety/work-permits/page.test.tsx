import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getWorkPermits: vi.fn(),
  getWorkPermitStats: vi.fn(),
}))

vi.mock('@/actions/safety', () => ({
  getWorkPermits: mocks.getWorkPermits,
  getWorkPermitStats: mocks.getWorkPermitStats,
}))

const panelProps = vi.hoisted(() => ({ last: vi.fn() }))

vi.mock('@/components/safety', () => ({
  WorkPermitListPanel: (props: Record<string, unknown>) => {
    panelProps.last(props)
    return null
  },
}))

import WorkPermitsPage from './page'

describe('作业票列表页装配', () => {
  it('加载成功时把列表与统计传给面板', async () => {
    mocks.getWorkPermits.mockResolvedValue({ code: 200, data: { items: [], total: 0 } })
    mocks.getWorkPermitStats.mockResolvedValue({ code: 200, data: { total: 0 } })
    await WorkPermitsPage().then((element) => renderToStaticMarkup(element))
    expect(mocks.getWorkPermits).toHaveBeenCalledWith(
      expect.objectContaining({
        pageKey: 'safety:ops-safety:work-permits',
        page: 1,
        pageSize: 20,
      }),
    )
    expect(panelProps.last).toHaveBeenCalledWith({
      initialList: { items: [], total: 0 },
      initialStats: { total: 0 },
      initialError: null,
    })
  })

  it('加载失败时传错误提示给面板', async () => {
    mocks.getWorkPermits.mockResolvedValue({ code: 500, message: '数据库不可用' })
    mocks.getWorkPermitStats.mockResolvedValue({ code: 200, data: null })
    await WorkPermitsPage().then((element) => renderToStaticMarkup(element))
    expect(panelProps.last).toHaveBeenCalledWith({
      initialList: null,
      initialStats: null,
      initialError: '数据库不可用',
    })
  })
})
