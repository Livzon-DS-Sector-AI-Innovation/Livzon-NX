/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useProductContextStore } from '@/stores/product-context'

const prodActions = vi.hoisted(() => ({
  getProductionLineStatus: vi.fn(),
}))
vi.mock('@/actions/production', () => prodActions)

import BoardNavBlocks from './board-nav-blocks'

const EXPECTED_TAB_TITLES = [
  '切换到 汇总（五产线聚合）',
  '切换到 霉酚酸 生产线与排产数据',
  // 林可 Tab 展示短名，悬停提示完整产品名
  '切换到 盐酸林可霉素 生产线与排产数据',
  '切换到 多拉菌素 生产线与排产数据',
  '切换到 L-苯丙氨酸 生产线与排产数据',
  '切换到 洛伐他汀 生产线与排产数据',
  '切换到 美伐他汀 生产线与排产数据',
  '切换到 L-色氨酸 生产线与排产数据',
  // 氟苯尼考 Tab 展示短名，悬停提示完整产品名
  '切换到 2%氟苯尼考预混剂 生产线与排产数据',
]

describe('BoardNavBlocks', () => {
  let root: Root
  let container: HTMLElement

  beforeEach(() => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    useProductContextStore.getState().setProductCode('FA')
    prodActions.getProductionLineStatus.mockReset()
    prodActions.getProductionLineStatus.mockResolvedValue({
      code: 200,
      message: 'success',
      data: { halted: [] },
    })
  })

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.clearAllMocks()
  })

  function render(props?: { hideCodes?: readonly string[] }) {
    act(() => {
      root.render(<BoardNavBlocks hideCodes={props?.hideCodes} />)
    })
  }

  it('renders the eight product tabs in the fixed business order', () => {
    render()
    const tabs = [...container.querySelectorAll('[title^="切换到"]')]
    expect(tabs.map((t) => t.getAttribute('title'))).toEqual(
      EXPECTED_TAB_TITLES,
    )
  })

  it('greys out halted line tabs with a halt badge and hover hint', async () => {
    prodActions.getProductionLineStatus.mockResolvedValue({
      code: 200,
      message: 'success',
      data: { halted: ['MC'] },
    })
    render()
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const haltedTag = container.querySelector('[data-testid="nav-halted-tag:MC"]')
    expect(haltedTag?.textContent).toBe('停产中')
    const haltedBlock = container.querySelector('[data-testid="nav-block:MC"]')
    expect(haltedBlock?.getAttribute('title')).toBe('切换到 霉酚酸（停产中）')
    // 未停产产品不带角标
    expect(
      container.querySelector('[data-testid="nav-halted-tag:DR"]'),
    ).toBeNull()
  })

  it('shows the florfenicol short name with the full name only in the hover title', () => {
    render()
    const tabs = [...container.querySelectorAll('[title^="切换到"]')]
    const fl = tabs[tabs.length - 1]
    expect(fl.getAttribute('title')).toBe(EXPECTED_TAB_TITLES[8])
    expect(fl.textContent).toContain('氟苯尼考')
    expect(fl.textContent).not.toContain('2%')
  })

  it('renders nine equal-flex tabs that share one row on wide screens', () => {
    render()
    const cols = [...container.querySelectorAll('.ant-col')]
    expect(cols.length).toBe(9)
    for (const col of cols) {
      // 弹性等宽：宽屏 9 块一行铺满，窄屏按 144px 基准自然换行
      expect(col.getAttribute('style')).toContain('flex-grow: 1')
      expect(col.getAttribute('style')).toContain('flex-basis: 144px')
    }
  })

  it('switches the shared product context on tab click', () => {
    render()
    const ty = container.querySelector(
      '[title="切换到 L-色氨酸 生产线与排产数据"]',
    )
    expect(ty).not.toBeNull()
    act(() => {
      ty!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    expect(useProductContextStore.getState().productCode).toBe('TY')
  })

  it('still hides tabs listed in hideCodes (scheduling page usage)', () => {
    render({ hideCodes: ['SUMMARY'] })
    const tabs = [...container.querySelectorAll('[title^="切换到"]')]
    expect(tabs.map((t) => t.getAttribute('title'))).toEqual(
      EXPECTED_TAB_TITLES.slice(1),
    )
  })
})
