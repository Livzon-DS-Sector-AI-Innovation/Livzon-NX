import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getGuardianRoster: vi.fn(),
}))

vi.mock('@/actions/safety', () => ({
  getGuardianRoster: mocks.getGuardianRoster,
}))

const panelProps = vi.hoisted(() => ({ last: vi.fn() }))

vi.mock('@/components/safety/GuardianRosterPanel', () => ({
  GuardianRosterPanel: (props: Record<string, unknown>) => {
    panelProps.last(props)
    return null
  },
}))

import GuardianRosterPage from './page'

describe('监护人名单页装配', () => {
  it('携带页面 key 拉取首屏并把数据传给面板', async () => {
    const list = { items: [], total: 0, workshops: [] }
    mocks.getGuardianRoster.mockResolvedValue({ code: 200, data: list })
    await GuardianRosterPage().then((element) => renderToStaticMarkup(element))
    expect(mocks.getGuardianRoster).toHaveBeenCalledWith(
      expect.objectContaining({
        pageKey: 'safety:ops-safety:guardian-roster',
        page: 1,
        pageSize: 20,
      }),
    )
    expect(panelProps.last).toHaveBeenCalledWith({
      initialList: list,
      initialError: null,
    })
  })

  it('加载失败时传错误提示给面板', async () => {
    mocks.getGuardianRoster.mockResolvedValue({ code: 500, message: '库不可用' })
    await GuardianRosterPage().then((element) => renderToStaticMarkup(element))
    expect(panelProps.last).toHaveBeenCalledWith(
      expect.objectContaining({ initialError: '库不可用' }),
    )
  })
})
