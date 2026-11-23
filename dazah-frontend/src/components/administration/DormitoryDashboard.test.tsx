/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  fetchDormitoryStats: vi.fn(),
  recommendDormitoryRooms: vi.fn(),
  submitDormitoryCheckin: vi.fn(),
}))

vi.mock('@/lib/api/mapped-feishu', () => api)

vi.mock('./DormitoryCheckinModal', () => ({
  default: (props: Record<string, unknown>) => (
    <div data-testid="checkin-modal" data-open={String(props.open)} />
  ),
}))

import DormitoryDashboard from './DormitoryDashboard'
import type { DormitoryOccupancyStats } from '@/types/administration'

let root: Root | null = null

function render(node: React.ReactNode) {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  root = createRoot(container)
  act(() => {
    root!.render(<QueryClientProvider client={client}>{node}</QueryClientProvider>)
  })
  return container
}

async function flush(rounds = 3) {
  for (let i = 0; i < rounds; i += 1) {
    await act(async () => {
      await Promise.resolve()
    })
  }
}

function bodyText(): string {
  document.querySelectorAll('svg').forEach((node) => node.remove())
  return document.body.textContent || ''
}

/** Card 的 loading 态会整体替换 children：轮询到统计渲染完成再操作卡片。 */
async function waitForStats(container: HTMLElement, rounds = 30) {
  for (let i = 0; i < rounds; i += 1) {
    if (container.textContent?.includes('总房间')) return
    await flush(2)
  }
  throw new Error('统计卡片未渲染')
}

afterEach(() => {
  act(() => root?.unmount())
  root = null
  document.body.innerHTML = ''
  vi.clearAllMocks()
})

const stats: DormitoryOccupancyStats = {
  total_rooms: 53,
  empty_rooms: 2,
  full_rooms: 6,
  partial_rooms: 45,
  total_beds: 241,
  occupied_beds: 160,
  occupancy_rate: 0.664,
  empty_room_list: [
    {
      room_no: '65-5-101',
      building: '65',
      unit: '5',
      room_type: '两人间',
      dorm_type: '男生宿舍',
      bed_count: 2,
      occupied: 0,
      vacant: 2,
    },
    {
      room_no: '65-5-102',
      building: '65',
      unit: '5',
      room_type: '两人间',
      dorm_type: '女生宿舍',
      bed_count: 2,
      occupied: 0,
      vacant: 2,
    },
  ],
  full_room_list: [
    {
      room_no: '65-3-101',
      building: '65',
      unit: '3',
      room_type: '五人间',
      dorm_type: '男生宿舍',
      bed_count: 5,
      occupied: 5,
      vacant: 0,
    },
  ],
  synced_at: '2026-11-20T00:00:00Z',
}

describe('DormitoryDashboard', () => {
  it('renders occupancy stats and the checkin entry', async () => {
    api.fetchDormitoryStats.mockResolvedValue(stats)
    const container = render(<DormitoryDashboard />)
    await waitForStats(container)
    const text = bodyText()
    expect(text).toContain('宿舍入住概览')
    expect(text).toContain('53')
    expect(text).toContain('66')
    expect(text).toContain('点击查看房间')
    expect(bodyText()).toContain('新员工入住')
  })

  it('shows the empty-room drawer when clicking the empty-room card', async () => {
    api.fetchDormitoryStats.mockResolvedValue(stats)
    const container = render(<DormitoryDashboard />)
    await waitForStats(container)
    const emptyCard = container.querySelector('button.cursor-pointer')
    expect(emptyCard).toBeTruthy()
    await act(async () => {
      ;(emptyCard as HTMLButtonElement).click()
      await Promise.resolve()
    })
    await flush(5)
    const text = bodyText()
    expect(text).toContain('空房间列表')
    expect(text).toContain('65-5-101')
    expect(text).toContain('65-5-102')
  })

  it('shows the full-room drawer with full rooms', async () => {
    api.fetchDormitoryStats.mockResolvedValue(stats)
    const container = render(<DormitoryDashboard />)
    await waitForStats(container)
    const clickable = Array.from(container.querySelectorAll('button.cursor-pointer'))
    expect(clickable.length).toBeGreaterThanOrEqual(2)
    await act(async () => {
      ;(clickable[1] as HTMLButtonElement).click()
      await Promise.resolve()
    })
    await flush(5)
    const text = bodyText()
    expect(text).toContain('满人房间列表')
    expect(text).toContain('65-3-101')
  })

  it('degrades to an error notice when stats cannot load', async () => {
    api.fetchDormitoryStats.mockRejectedValue(new Error('读取宿舍入住统计失败'))
    render(<DormitoryDashboard />)
    // 组件查询 retry=1（约 1s 退避后重试），等重试耗尽后才渲染错误态
    await new Promise((resolve) => setTimeout(resolve, 1500))
    await flush(5)
    expect(bodyText()).toContain('读取宿舍入住统计失败')
  })
})
