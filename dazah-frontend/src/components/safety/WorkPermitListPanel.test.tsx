/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getWorkPermits: vi.fn(),
  getWorkPermitStats: vi.fn(),
  getWorkPermitMeta: vi.fn(),
  canOperate: true,
  canAccess: true,
}))

vi.mock('@/actions/safety', () => ({
  getWorkPermits: mocks.getWorkPermits,
  getWorkPermitStats: mocks.getWorkPermitStats,
  getWorkPermitMeta: mocks.getWorkPermitMeta,
  WORK_PERMITS_PAGE_KEY: 'safety:ops-safety:work-permits',
}))

vi.mock('@/hooks/usePagePermissions', () => ({
  usePagePermissions: () => ({
    canAccess: mocks.canAccess,
    canQuery: mocks.canAccess,
    canOperate: mocks.canOperate,
    canDelete: false,
    canExport: false,
    canImport: false,
    canSync: false,
    canApprove: true,
    canReject: true,
  }),
}))

// happy-dom 解析 antd SVG 会截断 DOM：统一把图标替换为空占位
vi.mock('@ant-design/icons', () => {
  const Icon = () => null
  return {
    ReloadOutlined: Icon,
    ArrowUpOutlined: Icon,
    PlusOutlined: Icon,
  }
})

import { WorkPermitListPanel } from './WorkPermitListPanel'

const STATS = {
  total: 2,
  draft: 1,
  pending_approval: 1,
  approved: 0,
  active: 0,
  completed: 0,
  rejected: 0,
  cancelled: 0,
  my_pending_approvals: 1,
}

const ITEMS = [
  {
    id: 'p1',
    permit_no: 'DH-20261106-001',
    permit_type: 'hot_work',
    permit_level: 'grade2',
    status: 'pending_approval',
    apply_department: '一车间',
    work_description: '罐区动火',
    work_location: '罐区东',
    planned_start_time: null,
    planned_end_time: null,
  },
  {
    id: 'p2',
    permit_no: 'MB-20261106-001',
    permit_type: 'blind_plate',
    permit_level: 'none',
    status: 'draft',
    apply_department: '二车间',
    work_description: '更换盲板',
    work_location: 'R101',
    planned_start_time: null,
    planned_end_time: null,
  },
]

const META = {
  permit_types: [
    { value: 'hot_work', label: '动火作业', no_prefix: 'DH' },
    { value: 'blind_plate', label: '盲板抽堵作业', no_prefix: 'MB' },
  ],
  level_options: {
    hot_work: [
      { value: 'special', label: '特级' },
      { value: 'grade1', label: '一级' },
      { value: 'grade2', label: '二级' },
    ],
    blind_plate: [{ value: 'none', label: '不分级别' }],
  },
  person_roles: {},
  measures: {},
  type_fields: {},
  risk_identification_options: [],
  gas_types: ['hot_work'],
  gas_cycle_minutes: { hot_work: 60 },
  certificate_categories: [],
}

function flush() {
  return new Promise((resolve) => setTimeout(resolve, 60))
}

function buttons(text: string) {
  // antd 两个汉字按钮会在中间插入空格（如「重 试」），统一去掉空白再匹配
  return Array.from(
    document.body.querySelectorAll<HTMLButtonElement>('button'),
  ).filter((b) => b.textContent?.replace(/\s/g, '').includes(text))
}

beforeEach(() => {
  mocks.getWorkPermits.mockResolvedValue({
    code: 200,
    data: { items: ITEMS, total: ITEMS.length, page: 1, page_size: 20 },
  })
  mocks.getWorkPermitStats.mockResolvedValue({ code: 200, data: STATS })
  mocks.getWorkPermitMeta.mockResolvedValue({ code: 200, data: META })
})

describe('作业票列表面板', () => {
  let root: Root | undefined
  let container: HTMLElement | undefined

  beforeEach(() => {
    container = document.body.appendChild(document.createElement('div'))
  })

  it('渲染统计卡、编号链接与状态标签', async () => {
    await act(async () => {
      root = createRoot(container!)
      root.render(<WorkPermitListPanel initialList={null} initialStats={STATS} initialError={null} />)
    })
    await flush()
    expect(
      document.body.textContent?.includes('待我审批：1'),
    ).toBe(true)
    expect(
      document.body.textContent?.includes('DH-20261106-001'),
    ).toBe(true)
    expect(
      document.body.textContent?.includes('MB-20261106-001'),
    ).toBe(true)
    expect(document.body.textContent?.includes('审批中')).toBe(true)
    const links = Array.from(document.body.querySelectorAll('a')).filter((a) =>
      (a.getAttribute('href') ?? '').includes('/safety/work-permits/'),
    )
    expect(links.length).toBeGreaterThanOrEqual(2)
  })

  it('点击状态统计卡按状态重新加载', async () => {
    await act(async () => {
      root = createRoot(container!)
      root.render(<WorkPermitListPanel initialList={null} initialStats={STATS} initialError={null} />)
    })
    await flush()
    const pendingCard = buttons('审批中：1')[0]
    expect(pendingCard).toBeTruthy()
    await act(async () => {
      pendingCard!.click()
    })
    await flush()
    expect(mocks.getWorkPermits).toHaveBeenCalledWith(
      expect.objectContaining({ status: 'pending_approval', page: 1 }),
    )
  })

  it('加载失败展示错误提示', async () => {
    mocks.getWorkPermits.mockResolvedValueOnce({
      code: 500,
      message: '后端异常',
    })
    await act(async () => {
      root = createRoot(container!)
      root.render(<WorkPermitListPanel initialList={null} initialStats={STATS} initialError={null} />)
    })
    await flush()
    // PlatformNotice 正文展示简明 message；完整 description 收进「了解访问规则」弹窗
    expect(document.body.textContent?.includes('作业票列表加载失败')).toBe(true)
    expect(buttons('重试').length).toBeGreaterThan(0)
  })
})
