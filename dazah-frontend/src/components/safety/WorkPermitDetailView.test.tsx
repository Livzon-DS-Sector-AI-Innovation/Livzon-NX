/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getWorkPermitMeta: vi.fn(),
  getWorkPermitDetail: vi.fn(),
  approveWorkPermitNode: vi.fn(),
  rejectWorkPermitNode: vi.fn(),
  submitWorkPermit: vi.fn(),
  verifyWorkPermit: vi.fn(),
  acceptWorkPermit: vi.fn(),
  cancelWorkPermit: vi.fn(),
  addWorkPermitGasAnalysis: vi.fn(),
  addWorkPermitRelation: vi.fn(),
  getApproverConfigs: vi.fn(),
  getWorkPermits: vi.fn(),
  canOperate: true,
  canAccess: true,
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

vi.mock('@/actions/safety', () => ({
  getWorkPermitMeta: mocks.getWorkPermitMeta,
  getWorkPermitDetail: mocks.getWorkPermitDetail,
  approveWorkPermitNode: mocks.approveWorkPermitNode,
  rejectWorkPermitNode: mocks.rejectWorkPermitNode,
  submitWorkPermit: mocks.submitWorkPermit,
  verifyWorkPermit: mocks.verifyWorkPermit,
  acceptWorkPermit: mocks.acceptWorkPermit,
  cancelWorkPermit: mocks.cancelWorkPermit,
  addWorkPermitGasAnalysis: mocks.addWorkPermitGasAnalysis,
  addWorkPermitRelation: mocks.addWorkPermitRelation,
  getApproverConfigs: mocks.getApproverConfigs,
  getWorkPermits: mocks.getWorkPermits,
}))

vi.mock('@/hooks/usePagePermissions', () => ({
  usePagePermissions: () => ({
    canAccess: mocks.canAccess,
    canQuery: mocks.canAccess,
    canOperate: mocks.canOperate,
    canDelete: false,
    canApprove: true,
    canReject: true,
  }),
}))

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>()
  const { createElement } = await import('react')
  const DatePickerStub = (
    props: {
      value?: unknown
      onChange?: (value: unknown) => void
    },
  ) =>
    createElement('input', {
      'data-testid': 'date-picker-stub',
      value: props.value ? String(props.value) : '',
      onChange: (event: { target: { value: string } }) => {
        const raw = event.target.value
        // 组件按 dayjs 形状消费（toISOString/format），直接给同形状的普通对象
        props.onChange?.(
          raw
            ? ({
                toISOString: () =>
                  new Date(raw.replace(' ', 'T') + ':00Z').toISOString(),
                format: () => raw,
              } as never)
            : null,
        )
      },
    })
  return {
    ...actual,
    DatePicker: Object.assign(DatePickerStub, { RangePicker: DatePickerStub }),
    message: mocks.message,
  }
})

vi.mock('@ant-design/icons', () => {
  const Icon = () => null
  return { ReloadOutlined: Icon }
})

import { WorkPermitDetailView } from './WorkPermitDetailView'

const META = {
  permit_types: [{ value: 'hot_work', label: '动火作业', no_prefix: 'DH' }],
  level_options: { hot_work: [{ value: 'grade2', label: '二级' }] },
  person_roles: {},
  measures: {
    hot_work: [
      { key: 'm1', text: '清理周边可燃物' },
      { key: 'm2', text: '办理动火证' },
    ],
  },
  type_fields: {},
  risk_identification_options: [],
  gas_types: ['hot_work'],
  gas_cycle_minutes: { hot_work: 60 },
  certificate_categories: [],
  nodes: {
    hot_work: [
      { key: 'apply', name: '车间审批', kind: 'approve', levels: null },
    ],
  },
}

const DETAIL = {
  id: 'p1',
  permit_no: 'DH-20261106-001',
  permit_type: 'hot_work',
  permit_level: 'grade2',
  status: 'pending_approval',
  apply_department: '一车间',
  apply_time: '2026-11-06T08:00:00Z',
  work_description: '罐区动火',
  work_location: '罐区东',
  work_unit: '维修班',
  planned_start_time: '2026-11-07T08:00:00Z',
  planned_end_time: '2026-11-07T18:00:00Z',
  actual_start_time: null,
  actual_end_time: null,
  persons: [
    {
      role: 'work_leader',
      name: '张三',
      certificate_id: 'c1',
      certificate_no: 'DJ-001',
      certificate_valid: null,
      certificate_status: null,
    },
    { role: 'worker', name: '李四', certificate_id: null },
  ],
  risk_identifications: ['动火产生火花'],
  safety_measures: [{ key: 'm1', status: 'yes', fills: { 具体距离: '5米' } }],
  type_data: { 动火等级: '二级' },
  related_legacy_no_text: 'DH-20260101-001',
  approval_round: 1,
  current_node_seq: 1,
  reject_opinion: null,
  remark: null,
  nodes: [
    {
      id: 'n1',
      round: 1,
      seq: 1,
      node_key: 'apply',
      node_name: '车间审批',
      node_kind: 'approve',
      status: 'pending',
      assigned_approver_name: '王主任',
      acted_by_name: null,
      acted_at: null,
      opinion: null,
    },
  ],
  gas_analyses: [],
  relations: [
    {
      related_permit_id: 'p2',
      related_permit_no: 'MB-20261106-001',
      related_permit_type: 'blind_plate',
      related_permit_status: 'approved',
    },
  ],
  attachments: [{ id: 'a1', category: 'sketch', file_name: '位置图.png', size_bytes: 10 }],
  next_gas_due_at: null,
  gas_overdue: false,
}

let root: Root | undefined

function flush(ms = 60) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function buttons(text: string) {
  return Array.from(
    document.body.querySelectorAll<HTMLButtonElement>('button'),
  ).filter((b) => b.textContent?.replace(/\s/g, '').includes(text))
}

beforeEach(() => {
  mocks.getWorkPermitMeta.mockResolvedValue({ code: 200, data: META })
  mocks.getWorkPermitDetail.mockResolvedValue({ code: 200, data: DETAIL })
  mocks.approveWorkPermitNode.mockResolvedValue({ code: 200, data: null })
  mocks.rejectWorkPermitNode.mockResolvedValue({ code: 200, data: null })
  mocks.submitWorkPermit.mockResolvedValue({ code: 200, data: { warnings: [] } })
  mocks.cancelWorkPermit.mockResolvedValue({ code: 200, data: null })
  mocks.getApproverConfigs.mockResolvedValue({
    code: 200,
    data: { items: [] },
  })
  mocks.getWorkPermits.mockResolvedValue({
    code: 200,
    data: { items: [], total: 0 },
  })
})

afterEach(async () => {
  if (root) {
    await act(async () => {
      root!.unmount()
    })
    root = undefined
  }
  document.body.replaceChildren()
  vi.clearAllMocks()
})

async function renderDetail(overrides: Record<string, unknown> = {}) {
  const container = document.body.appendChild(document.createElement('div'))
  await act(async () => {
    root = createRoot(container)
    root!.render(
      <WorkPermitDetailView
        initialDetail={{ ...DETAIL, ...overrides } as never}
      />,
    )
  })
  await flush()
}

describe('作业票详情视图', () => {
  it('渲染票面、审批时间线、人员证件、措施与附件', async () => {
    await renderDetail()
    expect(document.body.textContent).toContain('DH-20261106-001')
    expect(document.body.textContent).toContain('动火作业')
    expect(document.body.textContent).toContain('罐区动火')
    // 审批时间线
    expect(document.body.textContent).toContain('车间审批')
    expect(document.body.textContent).toContain('指派：王主任')
    expect(document.body.textContent).toContain('待处理')
    // 人员证件链接与未关联提示
    expect(document.body.textContent).toContain('作业负责人：张三')
    expect(
      Array.from(document.body.querySelectorAll('a')).some((a) =>
        (a.getAttribute('href') ?? '').includes('/safety/work-certificates?cert=c1'),
      ),
    ).toBe(true)
    expect(document.body.textContent).toContain('（未关联证件）')
    // 票面信息 / 风险 / 措施 / 关联票 / 附件
    expect(document.body.textContent).toContain('动火等级')
    expect(document.body.textContent).toContain('具体距离=5米')
    expect(document.body.textContent).toContain('未确认')
    expect(
      Array.from(document.body.querySelectorAll('a')).some((a) =>
        (a.getAttribute('href') ?? '').endsWith('/safety/work-permits/p2'),
      ),
    ).toBe(true)
    expect(
      Array.from(document.body.querySelectorAll('a')).some((a) =>
        (a.getAttribute('href') ?? '').includes('/attachments/a1/preview'),
      ),
    ).toBe(true)
    // 气体分析卡（动火票）
    expect(document.body.textContent).toContain('复检间隔 60 分钟')
  })

  it('同意当前节点后刷新详情', async () => {
    await renderDetail()
    await act(async () => {
      buttons('同意')[0].click()
    })
    await flush()
    expect(mocks.approveWorkPermitNode).toHaveBeenCalledWith('p1', 'n1')
    expect(mocks.message.success).toHaveBeenCalledWith('已签批「车间审批」')
    expect(mocks.getWorkPermitDetail).toHaveBeenCalledWith('p1')
  })

  it('同意失败提示错误', async () => {
    mocks.approveWorkPermitNode.mockResolvedValue({ code: 500, message: '无权限' })
    await renderDetail()
    await act(async () => {
      buttons('同意')[0].click()
    })
    await flush()
    expect(mocks.message.error).toHaveBeenCalledWith('无权限')
  })

  it('驳回需填写意见，确认后调用驳回接口', async () => {
    await renderDetail()
    await act(async () => {
      buttons('驳回')[0].click()
    })
    await flush()
    // 空意见先被拦截
    await act(async () => {
      buttons('确认驳回')[0].click()
    })
    await flush()
    expect(mocks.message.warning).toHaveBeenCalledWith('请填写驳回意见')
    expect(mocks.rejectWorkPermitNode).not.toHaveBeenCalled()
    // 填写意见后确认
    const textarea = document.body.querySelector<HTMLTextAreaElement>(
      'textarea[placeholder="驳回意见（必填）"]',
    )
    expect(textarea).toBeTruthy()
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(
        HTMLTextAreaElement.prototype,
        'value',
      )?.set
      setter?.call(textarea!, '安全措施不足')
      textarea!.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await act(async () => {
      buttons('确认驳回')[0].click()
    })
    await flush()
    expect(mocks.rejectWorkPermitNode).toHaveBeenCalledWith(
      'p1',
      'n1',
      '安全措施不足',
    )
    expect(mocks.message.success).toHaveBeenCalledWith('已驳回')
  })

  it('草稿票作废需 Popconfirm 确认', async () => {
    await renderDetail({ status: 'draft' })
    await act(async () => {
      buttons('作废')[0].click()
    })
    await flush()
    // 测试环境 antd 默认英文 locale：Popconfirm 确认按钮为 OK
    const confirm = buttons('OK')
    expect(confirm.length).toBeGreaterThan(0)
    await act(async () => {
      confirm[confirm.length - 1].click()
    })
    await flush()
    expect(mocks.cancelWorkPermit).toHaveBeenCalledWith('p1')
    expect(mocks.message.success).toHaveBeenCalledWith('已作废')
  })
})

describe('作业票详情视图：气体 / 提交 / 关联', () => {
  beforeEach(() => {
    // 人员搜索走原生 fetch
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(
            JSON.stringify({
              data: { items: [{ id: 'ou_1', name: '王主任', department: '安全科' }] },
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

  it('渲染气体分析记录行与超期告警', async () => {
    await renderDetail({
      status: 'active',
      gas_overdue: true,
      next_gas_due_at: '2026-11-07T10:00:00Z',
      gas_analyses: [
        {
          id: 'g1',
          phase: 'pre_work',
          sampled_at: '2026-11-07T08:00:00Z',
          analysis_point: '罐区东',
          items: [{ name: '可燃气体', standard: '0', value: '12' }],
          oxygen_value: '21',
          analyst_name: '李四',
        },
      ],
    })
    expect(document.body.textContent).toContain('作业前分析')
    expect(document.body.textContent).toContain('罐区东')
    expect(document.body.textContent).toContain('可燃气体：12')
    expect(document.body.textContent).toContain('21')
    expect(document.body.textContent).toContain('李四')
    expect(document.body.textContent).toContain('气体复检已超期')
    // active + 操作权限 → 气体录入表单
    expect(document.body.textContent).toContain('录入复检')
  })

  async function pickFirstOption(selectInput: HTMLElement | null) {
    expect(selectInput).toBeTruthy()
    await act(async () => {
      selectInput!.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
    })
    await flush(40)
    const option = document.body.querySelector<HTMLElement>(
      '.ant-select-item-option',
    )
    expect(option, '下拉选项应出现').toBeTruthy()
    await act(async () => {
      option!.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      option!.click()
    })
    await flush(30)
  }

  it('草稿提交审批：选派节点审批人后提交', async () => {
    await renderDetail({ status: 'draft', approval_round: 0 })
    await act(async () => {
      buttons('提交审批')[0].click()
    })
    await flush()
    expect(document.body.textContent).toContain('提交审批（第 1 轮，逐级签批）')
    expect(document.body.textContent).toContain('车间审批')
    // 打开节点审批人下拉并选择
    const selectInput = document.body.querySelector<HTMLElement>(
      '.ant-modal input.ant-select-input',
    )
    expect(selectInput).toBeTruthy()
    await pickFirstOption(selectInput!)
    // 选择后提交按钮可用；精确匹配「提交」避免误点头部「提交审批」
    const submit = Array.from(
      document.body.querySelectorAll<HTMLButtonElement>('button'),
    ).filter((b) => b.textContent?.replace(/\s/g, '') === '提交' && !b.disabled)
    expect(submit.length, '提交按钮应可用').toBeGreaterThan(0)
    await act(async () => {
      submit[submit.length - 1].click()
    })
    await flush()
    expect(mocks.submitWorkPermit).toHaveBeenCalledWith('p1', [
      { node_key: 'apply', approver_user_id: 'ou_1' },
    ])
    expect(mocks.message.success).toHaveBeenCalledWith('已提交审批')
    expect(mocks.getWorkPermitDetail).toHaveBeenCalledWith('p1')
  })

  it('添加关联作业票：选择目标后关联', async () => {
    mocks.getWorkPermits.mockResolvedValue({
      code: 200,
      data: {
        items: [
          { id: 'p9', permit_no: 'SX-20261107-001', permit_type: 'height_work', permit_status: 'active' },
        ],
        total: 1,
      },
    })
    mocks.addWorkPermitRelation.mockResolvedValue({ code: 200, data: null })
    await renderDetail()
    await act(async () => {
      buttons('添加关联票')[0].click()
    })
    await flush()
    expect(document.body.textContent).toContain('添加关联作业票')
    const selectInput = document.body.querySelector<HTMLElement>(
      '.ant-drawer input.ant-select-input',
    )
    expect(selectInput).toBeTruthy()
    await pickFirstOption(selectInput!)
    // 精确匹配「关联」避免误点「添加关联票」
    const relate = Array.from(
      document.body.querySelectorAll<HTMLButtonElement>('button'),
    ).filter((b) => b.textContent?.replace(/\s/g, '') === '关联' && !b.disabled)
    expect(relate.length, '关联按钮应可用').toBeGreaterThan(0)
    await act(async () => {
      relate[relate.length - 1].click()
    })
    await flush()
    expect(mocks.addWorkPermitRelation).toHaveBeenCalledWith('p1', 'p9')
    expect(mocks.message.success).toHaveBeenCalledWith('关联已添加')
  })

  it('active 票录入气体复检记录', async () => {
    mocks.addWorkPermitGasAnalysis.mockResolvedValue({ code: 200, data: null })
    await renderDetail({ status: 'active' })
    const dates = Array.from(
      document.body.querySelectorAll<HTMLInputElement>(
        'input[data-testid="date-picker-stub"]',
      ),
    )
    expect(dates.length).toBeGreaterThan(0)
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        'value',
      )?.set
      setter?.call(dates[0], '2026-11-07 09:30')
      dates[0].dispatchEvent(new Event('input', { bubbles: true }))
    })
    const point = document.body.querySelector<HTMLInputElement>(
      'input[placeholder="分析部位"]',
    )
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        'value',
      )?.set
      setter?.call(point!, '罐区东')
      point!.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await act(async () => {
      buttons('录入复检')[0].click()
    })
    await flush()
    expect(mocks.addWorkPermitGasAnalysis).toHaveBeenCalledWith(
      'p1',
      expect.objectContaining({
        phase: 'on_duty',
        analysis_point: '罐区东',
        analyst_name: null,
      }),
    )
    expect(mocks.message.success).toHaveBeenCalledWith('复检记录已录入')
  })
})
