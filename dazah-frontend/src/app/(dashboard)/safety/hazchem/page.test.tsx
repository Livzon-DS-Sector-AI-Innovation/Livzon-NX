import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

const actions = vi.hoisted(() => ({
  getHazardousChemicals: vi.fn(),
}))

vi.mock('@/actions/safety', () => actions)

const panelProps = vi.hoisted(() => ({
  last: vi.fn(),
}))

vi.mock('@/components/safety', () => ({
  HazchemPanel: (props: Record<string, unknown>) => {
    panelProps.last(props)
    return null
  },
}))

import HazchemPage from './page'

describe('HazchemPage', () => {
  it('加载成功时把档案作为初始数据传给面板', async () => {
    actions.getHazardousChemicals.mockResolvedValue({
      code: 200,
      message: 'success',
      data: { items: [{ id: 'c-1', name: '乙醇' }], total: 1 },
    })
    await HazchemPage().then((element) => renderToStaticMarkup(element))
    expect(actions.getHazardousChemicals).toHaveBeenCalledWith({
      page_size: 200,
    })
    expect(panelProps.last).toHaveBeenCalledWith({
      pageKey: 'safety:site-mgmt:hazchem-msds',
      initialChemicals: [{ id: 'c-1', name: '乙醇' }],
      initialError: null,
    })
  })

  it('请求失败时给面板空档案与错误提示', async () => {
    actions.getHazardousChemicals.mockResolvedValue({
      code: 500,
      message: '数据库不可用',
    })
    await HazchemPage().then((element) => renderToStaticMarkup(element))
    expect(panelProps.last).toHaveBeenCalledWith({
      pageKey: 'safety:site-mgmt:hazchem-msds',
      initialChemicals: [],
      initialError: '数据库不可用',
    })
  })

  it('请求抛异常时静默降级为空档案', async () => {
    actions.getHazardousChemicals.mockRejectedValue(new Error('down'))
    await HazchemPage().then((element) => renderToStaticMarkup(element))
    expect(panelProps.last).toHaveBeenCalledWith({
      pageKey: 'safety:site-mgmt:hazchem-msds',
      initialChemicals: [],
      initialError: null,
    })
  })
})
