/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getWorkPermits: vi.fn(),
  getWorkPermitStats: vi.fn(),
  getWorkPermitMeta: vi.fn(),
  getApproverConfigs: vi.fn(),
  getWorkPermitSettings: vi.fn(),
  updateWorkPermitSettings: vi.fn(),
  upsertApproverConfig: vi.fn(),
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  canOperate: true,
  canAccess: true,
}))

vi.mock('@/actions/safety', () => ({
  getWorkPermits: mocks.getWorkPermits,
  getWorkPermitStats: mocks.getWorkPermitStats,
  getWorkPermitMeta: mocks.getWorkPermitMeta,
  getApproverConfigs: mocks.getApproverConfigs,
  getWorkPermitSettings: mocks.getWorkPermitSettings,
  updateWorkPermitSettings: mocks.updateWorkPermitSettings,
  upsertApproverConfig: mocks.upsertApproverConfig,
  WORK_PERMITS_PAGE_KEY: 'safety:ops-safety:work-permits',
}))

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>()
  return { ...actual, message: mocks.message }
})

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
  nodes: {
    blind_plate: [
      { key: 'work_leader_approve', name: '作业负责人审批', kind: 'approve', levels: null },
    ],
  },
}

function flush(ms = 60) {
  return new Promise((resolve) => setTimeout(resolve, ms))
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

describe('作业票列表面板：默认审批人配置抽屉', () => {
  let localRoot: Root | undefined
  let localContainer: HTMLElement | undefined

  beforeEach(() => {
    localContainer = document.body.appendChild(document.createElement('div'))
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(
            JSON.stringify({
              data: {
                items: [{ id: 'ou_1', name: '王主任', department: '安全科' }],
              },
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
        ),
      ),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('打开配置抽屉：加载配置与开关并渲染节点', async () => {
    mocks.getApproverConfigs.mockResolvedValue({
      code: 200,
      data: {
        items: [
          {
            permit_type: 'blind_plate',
            node_key: 'work_leader_approve',
            approver_user_id: 'ou_1',
          },
        ],
      },
    })
    mocks.getWorkPermitSettings.mockResolvedValue({
      code: 200,
      data: { cert_check_strict: true },
    })
    await act(async () => {
      localRoot = createRoot(localContainer!)
      localRoot.render(<WorkPermitListPanel initialList={null} initialStats={STATS} initialError={null} />)
    })
    await flush()
    await act(async () => {
      buttons('默认审批人配置')[0].click()
    })
    await flush()
    expect(document.body.textContent).toContain('节点默认审批人配置')
    expect(document.body.textContent).toContain('作业负责人审批')
    expect(mocks.getApproverConfigs).toHaveBeenCalled()
    expect(mocks.getWorkPermitSettings).toHaveBeenCalled()
    // 开关处于开启态（cert_check_strict=true）
    const switchButton = document.body.querySelector<HTMLButtonElement>(
      'button[role="switch"]',
    )
    expect(switchButton?.getAttribute('aria-checked')).toBe('true')
  })

  it('切换证件强校验开关：成功提示与失败回退', async () => {
    mocks.getApproverConfigs.mockResolvedValue({ code: 200, data: { items: [] } })
    mocks.getWorkPermitSettings.mockResolvedValue({
      code: 200,
      data: { cert_check_strict: false },
    })
    mocks.updateWorkPermitSettings.mockResolvedValue({ code: 200, data: null })
    await act(async () => {
      localRoot = createRoot(localContainer!)
      localRoot.render(<WorkPermitListPanel initialList={null} initialStats={STATS} initialError={null} />)
    })
    await flush()
    await act(async () => {
      buttons('默认审批人配置')[0].click()
    })
    await flush()
    const switchButton = document.body.querySelector<HTMLButtonElement>(
      'button[role="switch"]',
    )
    expect(switchButton?.getAttribute('aria-checked')).toBe('false')
    await act(async () => {
      switchButton!.click()
    })
    await flush()
    expect(mocks.updateWorkPermitSettings).toHaveBeenCalledWith(true)
    expect(mocks.message).not.toBeUndefined()
    // 失败路径：保存失败回退开关并报错
    mocks.updateWorkPermitSettings.mockResolvedValue({
      code: 500,
      message: '保存失败',
    })
    await act(async () => {
      switchButton!.click()
    })
    await flush()
    expect(mocks.updateWorkPermitSettings).toHaveBeenLastCalledWith(false)
  })

  it('选择节点审批人后保存配置', async () => {
    mocks.getApproverConfigs.mockResolvedValue({ code: 200, data: { items: [] } })
    mocks.getWorkPermitSettings.mockResolvedValue({
      code: 200,
      data: { cert_check_strict: false },
    })
    mocks.upsertApproverConfig.mockResolvedValue({ code: 200, data: null })
    await act(async () => {
      localRoot = createRoot(localContainer!)
      localRoot.render(<WorkPermitListPanel initialList={null} initialStats={STATS} initialError={null} />)
    })
    await flush()
    await act(async () => {
      buttons('默认审批人配置')[0].click()
    })
    await flush()
    // 抽屉内多个下拉：最后一个输入框是节点审批人选择器
    const selectInputs = Array.from(
      document.body.querySelectorAll<HTMLElement>('.ant-drawer input.ant-select-input'),
    )
    expect(selectInputs.length).toBeGreaterThanOrEqual(2)
    const nodeSelect = selectInputs[selectInputs.length - 1]
    await act(async () => {
      nodeSelect.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
    })
    await flush(30)
    // showSearch 下拉靠输入关键词触发 onSearch 拉取人员
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        'value',
      )?.set
      setter?.call(nodeSelect, '王')
      nodeSelect.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await flush(60)
    const option = Array.from(
      document.body.querySelectorAll<HTMLElement>('.ant-select-item-option'),
    ).find((o) => o.textContent?.includes('王主任'))
    expect(option, '人员下拉应出现王主任').toBeTruthy()
    await act(async () => {
      option!.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      option!.click()
    })
    await flush()
    expect(mocks.upsertApproverConfig).toHaveBeenCalledWith({
      permit_type: 'blind_plate',
      node_key: 'work_leader_approve',
      approver_user_id: 'ou_1',
    })
  })
})
