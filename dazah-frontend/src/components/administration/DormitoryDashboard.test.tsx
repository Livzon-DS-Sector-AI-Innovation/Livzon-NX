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
  // 弹窗本体由 DormitoryCheckinModal.test.tsx 覆盖；这里暴露两个回调的触发入口
  default: (props: Record<string, unknown>) => (
    <div data-testid="checkin-modal" data-open={String(props.open)}>
      <button
        data-testid="checkin-close"
        onClick={() => (props.onClose as () => void)()}
      />
      <button
        data-testid="checkin-done"
        onClick={() => (props.onCheckedin as () => void)()}
      />
    </div>
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

function bodyText(): string {
  document.querySelectorAll('svg').forEach((node) => node.remove())
  return document.body.textContent || ''
}

/** Card 的 loading 态会整体替换 children：轮询到统计渲染完成再操作卡片。 */
async function waitForStats(container: HTMLElement) {
  for (let i = 0; i < 80; i += 1) {
    if (container.textContent?.includes('总房间')) return
    // 组件内置 QueryClient 的结果通知走真实定时器：在 act 内让出事件循环
    // 时间，保证触发的重渲染在 act 退出时被冲刷（只让微任务等不到通知）
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 25))
    })
  }
  throw new Error('统计卡片未渲染')
}

afterEach(async () => {
  await act(async () => root?.unmount())
  root = null
  // 卸载后让出一轮宏任务：React 调度器里排队的被动副作用必须在
  // happy-dom 环境销毁之前执行完
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
  document.body.innerHTML = ''
  vi.clearAllMocks()
})

/** 轮询到 body 出现全部文本（Drawer 挂在 portal，渲染依赖动画帧与定时器）。 */
async function waitForBodyText(texts: string[], rounds = 60) {
  for (let i = 0; i < rounds; i += 1) {
    const text = bodyText()
    if (texts.every((item) => text.includes(item))) return
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 25))
    })
  }
  throw new Error(`未渲染出文本: ${texts.join(' / ')}`)
}

/** 去空白后按文案找按钮（antd 两字按钮会渲染成「刷 新」）。 */
function buttonIn(root: ParentNode, text: string): HTMLButtonElement | undefined {
  const needle = text.replace(/\s/g, '')
  return [...root.querySelectorAll('button')].find((button) =>
    (button.textContent ?? '').replace(/\s/g, '').includes(needle),
  )
}

/** 轮询到条件成立（Modal/Drawer 与查询通知都依赖真实定时器）。 */
async function until(condition: () => boolean, message: string) {
  for (let i = 0; i < 80; i += 1) {
    if (condition()) return
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 25))
    })
  }
  throw new Error(message)
}

async function click(element: Element | undefined | null) {
  expect(element).toBeTruthy()
  await act(async () => {
    element!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  })
}

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
    })
    await waitForBodyText(['空房间列表', '65-5-101', '65-5-102'])
  })

  it('shows the full-room drawer with full rooms', async () => {
    api.fetchDormitoryStats.mockResolvedValue(stats)
    const container = render(<DormitoryDashboard />)
    await waitForStats(container)
    const clickable = Array.from(container.querySelectorAll('button.cursor-pointer'))
    expect(clickable.length).toBeGreaterThanOrEqual(2)
    await act(async () => {
      ;(clickable[1] as HTMLButtonElement).click()
    })
    await waitForBodyText(['满人房间列表', '65-3-101'])
  })

  it('degrades to an error notice when stats cannot load', async () => {
    api.fetchDormitoryStats.mockRejectedValue(new Error('读取宿舍入住统计失败'))
    render(<DormitoryDashboard />)
    // 组件查询 retry=1（约 1s 退避后重试）：轮询到重试耗尽后渲染的错误态
    await waitForBodyText(['读取宿舍入住统计失败'])
    expect(bodyText()).not.toContain('总房间')
  })

  it('刷新：重新请求入住统计', async () => {
    api.fetchDormitoryStats.mockResolvedValue(stats)
    const container = render(<DormitoryDashboard />)
    await waitForStats(container)
    const calls = api.fetchDormitoryStats.mock.calls.length

    await click(buttonIn(container, '刷新'))

    await until(
      () => api.fetchDormitoryStats.mock.calls.length > calls,
      '刷新未重新请求统计',
    )
  })

  it('新员工入住：打开办理弹窗，关闭后收起', async () => {
    api.fetchDormitoryStats.mockResolvedValue(stats)
    const container = render(<DormitoryDashboard />)
    await waitForStats(container)

    await click(buttonIn(container, '新员工入住'))
    await until(
      () => document.querySelector('[data-testid="checkin-modal"][data-open="true"]') !== null,
      '办理弹窗未打开',
    )

    await click(document.querySelector('[data-testid="checkin-close"]'))

    await until(
      () => document.querySelector('[data-testid="checkin-modal"]') === null,
      '办理弹窗未关闭',
    )
  })

  it('办理入住成功：刷新统计并通知父级', async () => {
    api.fetchDormitoryStats.mockResolvedValue(stats)
    const onCheckinSuccess = vi.fn()
    const container = render(<DormitoryDashboard onCheckinSuccess={onCheckinSuccess} />)
    await waitForStats(container)
    await click(buttonIn(container, '新员工入住'))
    await until(
      () => document.querySelector('[data-testid="checkin-done"]') !== null,
      '办理弹窗未打开',
    )
    const calls = api.fetchDormitoryStats.mock.calls.length

    await click(document.querySelector('[data-testid="checkin-done"]'))

    await until(
      () => api.fetchDormitoryStats.mock.calls.length > calls,
      '办理成功后未刷新统计',
    )
    expect(onCheckinSuccess).toHaveBeenCalledTimes(1)
  })

  it('点击抽屉关闭按钮：收起房间列表', async () => {
    api.fetchDormitoryStats.mockResolvedValue(stats)
    const container = render(<DormitoryDashboard />)
    await waitForStats(container)
    await click(container.querySelector('button.cursor-pointer'))
    await waitForBodyText(['空房间列表', '65-5-101'])

    await click(document.querySelector('.ant-drawer-close'))

    await until(
      () => document.querySelector('.ant-drawer-open') === null,
      '抽屉未关闭',
    )
  })
})
