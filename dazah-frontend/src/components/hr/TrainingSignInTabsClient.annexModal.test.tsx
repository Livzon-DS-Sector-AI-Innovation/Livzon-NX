/* @vitest-environment happy-dom */
/**
 * 培训资料「选择培训附件内容」弹窗打开链路回归。
 *
 * 修复的缺陷：计划切换后立即选项目（或条目拉取失败）时 planSections 仍是空，
 * handleItemChange 只读闭包快照导致不自动弹窗，且 modalSections 置空后
 * "选择培训附件内容"按钮仍打开过期的空弹窗（显示"附件未解析出可选的文件清单内容"）。
 * 修复后 openContentModal 在条目为空时兜底重拉，并把无附件/失败提示出来。
 */

import { act, createElement, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  fetchAnnualTrainingPlans: vi.fn(),
  fetchPlanItems: vi.fn(),
  fetchPlanAttachmentSections: vi.fn(),
  fetchUsedTrainingContent: vi.fn(),
  fetchTrainingSession: vi.fn(),
  fetchSessionDocuments: vi.fn(),
  fetchNewHires: vi.fn(),
  fetchTrainingPersonnelConfigs: vi.fn(),
  fetchTrainingDepartments: vi.fn(),
}))

const actions = vi.hoisted(() => ({
  createTrainingLedger: vi.fn(),
  markTrainingContentUsed: vi.fn(),
  upsertTrainingSession: vi.fn(),
  upsertTrainingDocument: vi.fn(),
  updateTrainingLedger: vi.fn(),
  resolveDocumentEntryContent: vi.fn(),
}))

const ui = vi.hoisted(() => ({
  message: { error: vi.fn(), success: vi.fn(), warning: vi.fn(), info: vi.fn() },
  modal: { confirm: vi.fn(), error: vi.fn(), success: vi.fn(), warning: vi.fn(), info: vi.fn() },
}))

const annexModal = vi.hoisted(() => ({ renders: [] as Array<Record<string, unknown>> }))

vi.mock('@/lib/api/client/hr', () => api)
vi.mock('@/actions/hr', () => actions)
vi.mock('@/actions/quality', () => ({ resolveDocumentEntryContent: actions.resolveDocumentEntryContent }))
vi.mock('@/lib/download', () => ({ downloadZip: vi.fn() }))
vi.mock('./trainingDept', () => ({
  with201SubDepts: (list: string[]) => list,
  unify201Dept: (d: string) => d,
  ensureDeptMappings: vi.fn(async () => undefined),
  useDeptMappings: () => ({ version: 0 }),
}))

vi.mock('./SignInSheetClient', () => ({ default: () => null }))
vi.mock('./TrainingEvaluationListClient', () => ({ default: () => null }))
vi.mock('./TrainingNotificationClient', () => ({ default: () => null }))
vi.mock('./TrainingPersonnelConfigModal', () => ({ default: () => null }))
vi.mock('./DocumentCatalogPickerModal', () => ({ default: () => null }))
vi.mock('./OralExamSheetClient', () => ({ default: () => null }))
vi.mock('./PracticalExamSheetClient', () => ({ default: () => null }))
vi.mock('./AiWrittenExamClient', () => ({ default: () => null }))
vi.mock('./TrainingAttachmentClient', () => ({ default: () => null }))

// 捕获弹窗收到的 sections，断言"按附件号匹配后的条目列表"
vi.mock('./AttachmentContentModal', async () => {
  const { createElement } = await import('react')
  return {
    default: (props: { open?: boolean; title?: string; sections?: Array<{ annex_no?: string }> }) => {
      annexModal.renders.push(props as Record<string, unknown>)
      if (!props?.open) return null
      const nos = (props.sections || []).map((s) => s.annex_no || '').join(',')
      return createElement(
        'div',
        { 'data-testid': 'annex-modal', 'data-sections': nos },
        props.title || '',
      )
    },
  }
})

vi.mock('@ant-design/icons', () => {
  const stub = () => null
  return Object.fromEntries(
    [
      'FormOutlined',
      'CheckSquareOutlined',
      'BellOutlined',
      'SettingOutlined',
      'BookOutlined',
      'SaveOutlined',
      'AuditOutlined',
      'ToolOutlined',
      'FileAddOutlined',
      'FolderOpenOutlined',
      'RobotOutlined',
      'UserAddOutlined',
      'PaperClipOutlined',
    ].map((name) => [name, stub]),
  )
})

vi.mock('antd', async () => {
  const { createElement } = await import('react')
  const Wrapper = ({ children }: { children?: ReactNode }) => createElement('div', null, children)
  const Button = ({
    children,
    disabled,
    loading,
    onClick,
  }: {
    children?: ReactNode
    disabled?: boolean
    loading?: boolean
    onClick?: () => void
  }) => createElement('button', { disabled: disabled || loading, onClick }, children)
  const Select = ({
    value,
    onChange,
    placeholder,
    options = [],
    mode,
  }: {
    value?: unknown
    onChange?: (v: unknown) => void
    placeholder?: string
    options?: Array<{ label?: ReactNode; value: unknown }>
    mode?: string
  }) =>
    createElement(
      'div',
      { 'data-select': placeholder || mode || 'select' },
      createElement('input', { readOnly: true, value: String(value ?? '') }),
      options.map((option) =>
        createElement(
          'button',
          {
            key: String(option.value),
            className: 'select-option',
            onClick: () => onChange?.(mode === 'multiple' ? [option.value] : option.value),
          },
          String(option.label ?? option.value),
        ),
      ),
    )
  return {
    App: { useApp: () => ({ message: ui.message, modal: ui.modal }) },
    AutoComplete: ({
      value,
      onChange,
      options = [],
    }: {
      value?: unknown
      onChange?: (v: string) => void
      options?: Array<{ value: string }>
    }) =>
      createElement(
        'div',
        { 'data-autocomplete': 'dept' },
        createElement('input', { readOnly: true, value: String(value ?? '') }),
        options.map((option) =>
          createElement(
            'button',
            { key: option.value, className: 'select-option', onClick: () => onChange?.(option.value) },
            option.value,
          ),
        ),
      ),
    Button,
    Card: Wrapper,
    Checkbox: Wrapper,
    Modal: ({ open, title, children }: { open?: boolean; title?: ReactNode; children?: ReactNode }) =>
      (open ? createElement('div', { 'data-testid': 'antd-modal' }, title, children) : null),
    Segmented: ({
      onChange,
      options = [],
    }: {
      onChange?: (v: unknown) => void
      options?: Array<{ label?: ReactNode; value: unknown }>
    }) =>
      createElement(
        'div',
        null,
        options.map((option) =>
          createElement(
            'button',
            { key: String(option.value), className: 'segmented-option', onClick: () => onChange?.(option.value) },
            String(option.label ?? option.value),
          ),
        ),
      ),
    Select,
    Space: Wrapper,
    Switch: ({ checked }: { checked?: boolean }) => createElement('input', { type: 'checkbox', checked: !!checked }),
    Tabs: ({ items = [] }: { items?: Array<{ key: string; children?: ReactNode }> }) =>
      createElement('div', null, items.map((item) => createElement('div', { key: item.key }, item.children))),
  }
})

import TrainingSignInTabsClient from './TrainingSignInTabsClient'

const PLAN_ID = 'plan-1'
const ITEM_REF_ANNEX4 = {
  id: 'item-annex4',
  training_month: '10月',
  content_textbook: '公共部门及车间相关文件巩固培训（详见附件四）',
  content_and_textbook: '',
  training_method: '脱产培训',
  sort_order: 3,
}
const ITEM_NO_REF = {
  id: 'item-noref',
  training_month: '11月',
  content_textbook: '车间安全生产知识培训',
  content_and_textbook: '',
  training_method: '脱产培训',
  sort_order: 4,
}
const PLAN_ITEMS = [ITEM_REF_ANNEX4, ITEM_NO_REF]
const SECTIONS = [1, 2, 3, 4, 5].map((n) => ({
  id: `sec-${n}`,
  annex_no: `附件${n}`,
  title: `附件${n}`,
  source_kind: 'docx_section',
  source_ref: String(n),
  attachment_id: 'att-1',
}))
const PLAN = { id: PLAN_ID, department: '201二车间（MC）', year: 2026, plan_level: '部门级' }

function findButton(scope: HTMLElement, text: string) {
  return Array.from(scope.querySelectorAll('button')).find((b) => b.textContent?.includes(text))
}

async function click(scope: HTMLElement, text: string) {
  const btn = findButton(scope, text)
  expect(btn, `找不到按钮：${text}`).toBeTruthy()
  await act(async () => {
    btn!.click()
  })
  await act(async () => {})
}

function annexModalDom(scope: HTMLElement) {
  return scope.querySelector('[data-testid="annex-modal"]') as HTMLElement | null
}

describe('培训资料：选择培训附件内容弹窗打开链路', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    vi.clearAllMocks()
    annexModal.renders.length = 0
    api.fetchAnnualTrainingPlans.mockResolvedValue({ code: 200, data: [PLAN] })
    api.fetchPlanItems.mockResolvedValue({ code: 200, data: PLAN_ITEMS })
    api.fetchUsedTrainingContent.mockResolvedValue([])
    api.fetchTrainingPersonnelConfigs.mockResolvedValue({ code: 200, data: [] })
    api.fetchTrainingDepartments.mockResolvedValue(['201二车间（MC）'])
    api.fetchTrainingSession.mockResolvedValue({})
    api.fetchSessionDocuments.mockResolvedValue([])
    api.fetchNewHires.mockResolvedValue({ code: 200, data: [] })
    actions.upsertTrainingSession.mockResolvedValue('session-1')
    actions.upsertTrainingDocument.mockResolvedValue(undefined)
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
  })

  /** 走到"已选部门级计划"状态；sectionsFirst 返回计划切换时首次条目拉取的结果 */
  async function selectDeptPlan(sectionsFirst: { code: number; data: unknown }) {
    api.fetchPlanAttachmentSections.mockResolvedValueOnce(sectionsFirst)
    await act(async () => {
      root.render(createElement(TrainingSignInTabsClient))
    })
    await act(async () => {})
    await click(container, '部门级培训')
    await click(container, '201二车间（MC）') // 部门 AutoComplete
    await click(container, '201二车间（MC）（2026）') // 关联年度计划
  }

  it('计划切换后立即选项目（条目未就绪）：兜底重拉并自动弹出匹配附件条目，按钮重开不再重复请求', async () => {
    await selectDeptPlan({ code: 200, data: [] }) // 首次拉取为空（模拟未就绪/失败）
    expect(api.fetchPlanAttachmentSections).toHaveBeenCalledTimes(1)
    expect(annexModalDom(container)).toBeNull()

    // 选定 10月/附件四 项目：openContentModal 兜底重拉并自动弹窗，只展示附件4
    api.fetchPlanAttachmentSections.mockResolvedValueOnce({ code: 200, data: SECTIONS })
    await click(container, '10月 公共部门及车间相关文件巩固培训（详见附件四）')
    expect(api.fetchPlanAttachmentSections).toHaveBeenCalledTimes(2)

    const modal = annexModalDom(container)
    expect(modal).not.toBeNull()
    expect(modal!.dataset.sections).toBe('附件4')

    // 条目已就绪后再点按钮：用最新 planSections 重算（修复打开过期空弹窗），不重复请求
    await click(container, '选择培训附件内容')
    expect(api.fetchPlanAttachmentSections).toHaveBeenCalledTimes(2)
    expect(annexModalDom(container)).not.toBeNull()
    expect(annexModalDom(container)!.dataset.sections).toBe('附件4')
  })

  it('计划无附件条目：提示上传附件，不再弹出空列表', async () => {
    await selectDeptPlan({ code: 200, data: [] })
    api.fetchPlanAttachmentSections.mockResolvedValue({ code: 200, data: [] })
    await click(container, '10月 公共部门及车间相关文件巩固培训（详见附件四）')

    expect(ui.message.warning).toHaveBeenCalledWith('该计划尚未上传附件，请先在年度培训计划页上传附件')
    expect(annexModalDom(container)).toBeNull()
  })

  it('条目拉取失败：提示重试而非静默吞掉', async () => {
    await selectDeptPlan({ code: 200, data: [] })
    api.fetchPlanAttachmentSections.mockRejectedValueOnce(new Error('network down'))
    await click(container, '10月 公共部门及车间相关文件巩固培训（详见附件四）')

    expect(ui.message.warning).toHaveBeenCalledWith('计划附件条目加载失败，请重新选择计划项目重试')
    expect(annexModalDom(container)).toBeNull()
  })

  it('条目已就绪时选项目：直接按附件号过滤，无额外请求；未引用附件号的项目回退展示全部条目', async () => {
    await selectDeptPlan({ code: 200, data: SECTIONS })
    expect(api.fetchPlanAttachmentSections).toHaveBeenCalledTimes(1)

    await click(container, '10月 公共部门及车间相关文件巩固培训（详见附件四）')
    expect(api.fetchPlanAttachmentSections).toHaveBeenCalledTimes(1)
    expect(annexModalDom(container)!.dataset.sections).toBe('附件4')

    // 关闭弹窗后换选未引用附件号的项目：回退展示全部 5 个条目
    const lastProps = annexModal.renders.at(-1) as { onClose?: () => void }
    await act(async () => {
      lastProps.onClose?.()
    })
    await act(async () => {})
    await click(container, '11月 车间安全生产知识培训')
    expect(annexModalDom(container)!.dataset.sections).toBe('附件1,附件2,附件3,附件4,附件5')
  })
})
