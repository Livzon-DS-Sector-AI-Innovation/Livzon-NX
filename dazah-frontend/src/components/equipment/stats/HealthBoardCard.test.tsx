/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  fetchHealthBoardClient: vi.fn(),
  useRouter: { push: vi.fn() },
}))

vi.mock('@/lib/api/equipment-client', () => ({
  fetchHealthBoardClient: api.fetchHealthBoardClient,
}))
vi.mock('next/navigation', () => ({
  useRouter: () => api.useRouter,
}))

import { HealthBoardCard } from './HealthBoardCard'

const board = {
  items: [
    {
      equipment_id: 'eq-1',
      equipment_no: 'LB-001',
      equipment_name: '离心泵A',
      workshop_code: '201-1',
      score: 42.5,
      grade: 'R' as const,
      metrics: null,
      snapshot_date: '2026-11-03',
    },
    {
      equipment_id: 'eq-2',
      equipment_no: 'LB-002',
      equipment_name: '离心泵B',
      workshop_code: '201-1',
      score: 70,
      grade: 'Y' as const,
      metrics: null,
      snapshot_date: '2026-11-03',
    },
  ],
  summary: { total: 12, G: 10, Y: 1, R: 1 },
}

describe('HealthBoardCard', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    api.fetchHealthBoardClient.mockResolvedValue(board)
    api.useRouter.push.mockClear()
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    vi.clearAllMocks()
  })

  it('renders grade summary and red/yellow equipment rows', async () => {
    act(() => {
      root.render(<HealthBoardCard />)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const text = document.body.textContent || ''
    expect(text).toContain('红档 1 台')
    expect(text).toContain('黄档 1 台')
    expect(text).toContain('绿档 10 台')
    // 绿档设备不进入关注列表，红/黄档按评分展示
    expect(text).toContain('离心泵A')
    expect(text).toContain('离心泵B')
  })

  it('navigates to the equipment ledger filtered by workshop on row click', async () => {
    act(() => {
      root.render(<HealthBoardCard />)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const row = [...document.body.querySelectorAll('[role="button"]')].find(
      (el) => el.textContent?.includes('离心泵A'),
    ) as HTMLElement | undefined
    expect(row).toBeTruthy()
    await act(async () => {
      row!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    expect(api.useRouter.push).toHaveBeenCalledWith(
      '/equipment?workshop=201-1&module=assets',
    )
  })

  it('shows retry entry when board load fails', async () => {
    api.fetchHealthBoardClient.mockRejectedValue(new Error('network'))
    act(() => {
      root.render(<HealthBoardCard />)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    expect(document.body.textContent).toContain('健康快照加载失败')
    expect(document.body.textContent).toContain('重试')
  })
})
