/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { EQUIPMENT_WORKSHOPS } from '@/lib/menu-config'
import { InspectionProgressCard } from './InspectionProgressCard'

const summaries = [
  {
    workshop_code: '101-2',
    date: '2026-10-13',
    total_devices: 49,
    inspected: 47,
    abnormal: 2,
    am_inspected: 47,
    pm_inspected: 46,
  },
]

function normalizedText(): string {
  return (document.body.textContent || '').replace(/\s+/g, '')
}

describe('InspectionProgressCard', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
  })

  function renderCard(items: typeof summaries = summaries) {
    act(() => {
      root.render(<InspectionProgressCard summaries={items} />)
    })
  }

  it('renders the summary bar with date, aggregate progress and abnormal count', () => {
    renderCard()
    const text = normalizedText()
    expect(text).toContain('今日巡检进度（2026-10-13）')
    expect(text).toContain('已接入1/9车间')
    expect(text).toContain('总进度47/49台')
    expect(text).toContain('上午47/49·下午46/49')
    expect(text).toContain('异常2台')
  })

  it('renders the enabled workshop as a linked row with progress numbers', () => {
    renderCard()
    const link = document.body.querySelector<HTMLAnchorElement>(
      'a[href="/equipment/inspection/101-2"]',
    )
    expect(link).toBeTruthy()
    expect(link!.textContent).toContain('101二车间')
    expect(link!.textContent).toContain('47/49')
    expect(link!.textContent).toContain('异常 2')
  })

  it('renders every unconnected workshop as a disabled "未接入" row', () => {
    renderCard()
    const unconnected = [...document.body.querySelectorAll('span')]
      .filter((el) => el.textContent?.trim() === '未接入')
    expect(unconnected).toHaveLength(EQUIPMENT_WORKSHOPS.length - 1)
    // 未接入车间不可点击
    expect(
      document.body.querySelector('a[href="/equipment/inspection/201-1"]'),
    ).toBeNull()
  })

  it('shows zero aggregates when no workshop is enabled', () => {
    renderCard([])
    const text = normalizedText()
    expect(text).toContain('已接入0/9车间')
    expect(text).toContain('总进度0/0台')
    expect(text).toContain('上午0/0·下午0/0')
    expect(document.body.querySelector('a[href^="/equipment/inspection/"]')).toBeNull()
  })
})
