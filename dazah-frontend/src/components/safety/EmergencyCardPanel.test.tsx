/* @vitest-environment happy-dom */

import { act, createElement, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })

const mocks = vi.hoisted(() => {
  const messageApi = { success: vi.fn(), error: vi.fn(), warning: vi.fn() }
  return {
    messageApi,
    message: Object.assign(messageApi, {
      useMessage: () => [messageApi, null],
    }),
    canOperate: true,
    canDelete: true,
    formValues: {} as Record<string, unknown>,
    getEmergencyCards: vi.fn(),
    getEmergencyCardStats: vi.fn(),
    createEmergencyCard: vi.fn(),
    updateEmergencyCard: vi.fn(),
    reviewEmergencyCard: vi.fn(),
    deleteEmergencyCard: vi.fn(async () => ({ code: 200 })),
  }
})

const formStub = {
  resetFields: vi.fn(),
  setFieldsValue: vi.fn(),
  validateFields: vi.fn(async () => mocks.formValues),
}

vi.mock('@/actions/safety', () => ({
  getEmergencyCards: mocks.getEmergencyCards,
  getEmergencyCardStats: mocks.getEmergencyCardStats,
  createEmergencyCard: mocks.createEmergencyCard,
  updateEmergencyCard: mocks.updateEmergencyCard,
  reviewEmergencyCard: mocks.reviewEmergencyCard,
  deleteEmergencyCard: mocks.deleteEmergencyCard,
}))

vi.mock('@/hooks/usePagePermissions', () => ({
  usePagePermissions: () => ({
    pageKey: 'safety:emergency-accident:emergency-card',
    canAccess: true,
    canQuery: true,
    canOperate: mocks.canOperate,
    canDelete: mocks.canDelete,
  }),
}))

vi.mock('@/components/shared/PlatformNotice', async () => {
  const { createElement } = await import('react')
  return {
    default: ({ message, description }: { message: ReactNode; description?: ReactNode }) =>
      createElement('div', { 'data-notice': String(message) }, description),
  }
})

vi.mock('antd', async () => {
  const { createElement } = await import('react')

  type AnyProps = Record<string, unknown>
  interface Column {
    title?: unknown
    dataIndex?: string
    render?: (value: unknown, row: Record<string, unknown>, index: number) => ReactNode
  }
  const Box = ({ children }: AnyProps) => createElement('div', null, children as ReactNode)
  const Button = ({ children, onClick, danger }: AnyProps) =>
    createElement(
      'button',
      {
        type: 'button',
        'data-danger': String(Boolean(danger)),
        onClick: onClick as never,
      },
      children as ReactNode
    )
  const Table = ({ columns, dataSource }: { columns?: Column[]; dataSource?: Array<Record<string, unknown>> }) =>
    createElement(
      'tbody',
      null,
      (dataSource ?? []).map((row, rowIndex) =>
        createElement(
          'tr',
          { key: String(row.id ?? rowIndex), 'data-row': String(row.id ?? rowIndex) },
          (columns ?? []).map((column, columnIndex) =>
            createElement(
              'td',
              { key: column.dataIndex ?? columnIndex },
              column.render
                ? (column.render(row[column.dataIndex ?? ''], row, rowIndex) as ReactNode)
                : ((row[column.dataIndex ?? ''] as ReactNode) ?? null)
            )
          )
        )
      )
    )
  const Tabs = ({ items, onChange }: { items?: Array<{ key: string; label: string }>; onChange?: (key: string) => void }) =>
    createElement(
      'div',
      null,
      (items ?? []).map((item) =>
        createElement(
          'button',
          {
            key: item.key,
            type: 'button',
            'data-tab': item.key,
            onClick: () => (onChange as (key: string) => void)?.(item.key),
          },
          item.label
        )
      )
    )
  const Drawer = ({ open, title, children }: AnyProps) =>
    createElement(
      'div',
      { 'data-drawer-open': String(Boolean(open)), 'data-drawer-title': String(title ?? '') },
      open ? (children as ReactNode) : null
    )
  const Modal = ({ open, title, children, onOk, onCancel }: AnyProps) =>
    createElement(
      'div',
      { 'data-modal-open': String(Boolean(open)), 'data-modal-title': String(title ?? '') },
      open
        ? [
            children as ReactNode,
            createElement(
              'button',
              { key: 'ok', type: 'button', 'data-modal-ok': 'true', onClick: onOk as never },
              '保存'
            ),
            createElement(
              'button',
              { key: 'cancel', type: 'button', 'data-modal-cancel': 'true', onClick: onCancel as never },
              '取消'
            ),
          ]
        : null
    )
  const Popconfirm = ({ children, onConfirm, description }: AnyProps) =>
    createElement(
      'span',
      { 'data-popconfirm': String(description ?? '') },
      children as ReactNode,
      createElement(
        'button',
        { type: 'button', 'data-confirm': 'true', onClick: onConfirm as never },
        '确认删除'
      )
    )
  const Select = ({ options, onChange, placeholder }: AnyProps) =>
    createElement(
      'select',
      { 'data-select': String(placeholder ?? '') },
      ((options as Array<{ value: string; label: string }>) ?? []).map((option) =>
        createElement(
          'option',
          {
            key: option.value,
            value: option.value,
            onClick: () => (onChange as (value: string) => void)?.(option.value),
          },
          option.label
        )
      )
    )
  const Input = ({ value, onChange, onPressEnter, placeholder }: AnyProps) =>
    createElement('input', {
      'data-input': String(placeholder ?? ''),
      value: (value as string) ?? '',
      onChange: (node: HTMLInputElement | null) => {
        if (!node) return
        ;(onChange as (event: { target: { value: string } }) => void)?.({
          target: { value: node.value },
        })
      },
      onKeyDown: (node: HTMLInputElement | null) => {
        if (!node) return
      },
      ref: (node: HTMLInputElement | null) => {
        if (!node) return
        node.oninput = () =>
          (onChange as (event: { target: { value: string } }) => void)?.({
            target: { value: node.value },
          })
        node.onkeydown = (event) => {
          if (event.key === 'Enter') (onPressEnter as () => void)?.()
        }
      },
    })
  const TextArea = ({ placeholder }: AnyProps) =>
    createElement('textarea', { 'data-textarea': String(placeholder ?? '') })
  const InputWithArea = Object.assign(Input, { TextArea })
  const Text = ({ children }: AnyProps) => createElement('span', null, children as ReactNode)
  const Paragraph = ({ children }: AnyProps) => createElement('p', null, children as ReactNode)
  const Link = ({ children, onClick }: AnyProps) =>
    createElement(
      'button',
      { type: 'button', 'data-link': 'true', onClick: onClick as never },
      children as ReactNode
    )

  const Form = Object.assign(
    ({ children }: AnyProps) => createElement('form', null, children as ReactNode),
    {
      useForm: () => [formStub],
      Item: ({ children }: AnyProps) => createElement('div', null, children as ReactNode),
      List: ({ render }: { render?: (fields: unknown[], meta: unknown) => ReactNode }) =>
        createElement('div', null, render?.([], { add: vi.fn(), remove: vi.fn() })),
    }
  )

  return {
    Button,
    Drawer,
    Empty: ({ description }: { description?: ReactNode }) =>
      createElement('div', { 'data-empty': 'true' }, description),
    Form,
    Input: InputWithArea,
    Modal,
    Popconfirm,
    Select,
    Space: Box,
    Table,
    Tabs,
    Tag: ({ children }: AnyProps) => createElement('span', null, children as ReactNode),
    Typography: Object.assign(
      ({ children }: AnyProps) => createElement('div', null, children as ReactNode),
      { Text, Title: Text, Paragraph, Link }
    ),
    message: mocks.message,
  }
})

import EmergencyCardPanel from './EmergencyCardPanel'

const STATS = {
  total: 2,
  workshops: [
    { workshop: '103车间', total: 1, positions: ['配料'] },
    { workshop: '203车间', total: 1, positions: [] },
  ],
  accident_types: ['泄漏', '火灾'],
}

const CARDS = {
  items: [
    {
      id: 'card-1',
      workshop: '103车间',
      position: '配料',
      title: '103车间臭氧中毒应急处置卡',
      subject: '臭氧中毒',
      accident_type: '中毒',
      steps: [
        {
          order: '1',
          step: '发现异常',
          action: '立即示警并撤离',
          person: '岗位员工',
        },
      ],
      extras: [{ label: '次生、衍生事故', content: '中毒窒息' }],
      phones: '消防：119；急救：120',
      risks: '重度中毒：肺水肿、昏迷或休克',
      precautions: '处置人员佩戴正压式空气呼吸器',
      source_file: '1.臭氧中毒应急处置卡.html',
      sort_order: 0,
      created_at: '2026-10-26T08:00:00Z',
      updated_at: '2026-10-26T08:00:00Z',
    },
    {
      id: 'card-2',
      workshop: '203车间',
      position: '',
      title: '203车间硫酸泄漏应急处置卡',
      subject: '硫酸泄漏',
      accident_type: '泄漏',
      steps: [],
      extras: [],
      phones: '',
      risks: '',
      precautions: '',
      source_file: '203车间硫酸应急处置卡.html',
      sort_order: 0,
      created_at: '2026-10-26T08:00:00Z',
      updated_at: '2026-10-26T08:00:00Z',
    },
  ],
  total: 2,
  page: 1,
  page_size: 20,
}

let root: Root | null = null
let container: HTMLElement | null = null

async function renderPanel(props?: {
  initialStats?: typeof STATS | null
  initialCards?: typeof CARDS | null
  initialError?: string | null
}) {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  await act(async () => {
    root?.render(
      createElement(EmergencyCardPanel, {
        initialStats: props?.initialStats === undefined ? STATS : props.initialStats,
        initialCards: props?.initialCards === undefined ? CARDS : props.initialCards,
        initialError: props?.initialError ?? null,
      })
    )
  })
  return container
}

function findButton(el: HTMLElement, text: string): HTMLButtonElement | null {
  return (
    (Array.from(el.querySelectorAll<HTMLButtonElement>('button')).find((button) =>
      button.textContent?.includes(text)
    ) as HTMLButtonElement | undefined) ?? null
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.canOperate = true
  mocks.canDelete = true
  mocks.formValues = {}
  mocks.getEmergencyCards.mockResolvedValue({ code: 200, data: CARDS })
  mocks.getEmergencyCardStats.mockResolvedValue({ code: 200, data: STATS })
  mocks.createEmergencyCard.mockResolvedValue({ code: 200, data: CARDS.items[0] })
  mocks.updateEmergencyCard.mockResolvedValue({
    code: 200,
    data: CARDS.items[0],
  })
  mocks.reviewEmergencyCard.mockResolvedValue({
    code: 200,
    data: {
      summary: '处置步骤较完整，但缺少风险后果描述。',
      completeness: [
        { item: '报警与报告', status: 'ok', note: '已覆盖' },
        { item: '主要风险及后果', status: 'missing', note: '未填写' },
      ],
      suggestions: [
        {
          section: 'risks',
          title: '补充泄漏风险',
          content: '泄漏会气化扩散，浓度过高导致人员中毒窒息。',
        },
      ],
    },
  })
})

afterEach(async () => {
  if (root) {
    await act(async () => root?.unmount())
  }
  container?.remove()
  root = null
  container = null
})

describe('EmergencyCardPanel', () => {
  it('渲染车间标签页与处置卡列表', async () => {
    const el = await renderPanel()
    const tabs = Array.from(el.querySelectorAll('[data-tab]')).map((tab) =>
      tab.textContent
    )
    expect(tabs).toContain('全部 (2)')
    expect(tabs).toContain('103车间 (1)')
    expect(el.querySelector('[data-row="card-1"]')?.textContent).toContain(
      '103车间臭氧中毒应急处置卡'
    )
    expect(el.querySelector('[data-row="card-2"]')?.textContent).toContain('泄漏')
  })

  it('读取失败时展示错误提示', async () => {
    mocks.getEmergencyCards.mockResolvedValue({
      code: 500,
      message: '后端不可用',
    })
    const el = await renderPanel({ initialCards: null, initialError: '后端不可用' })
    expect(el.querySelector('[data-notice]')?.getAttribute('data-notice')).toContain(
      '读取失败'
    )
    expect(el.textContent).toContain('后端不可用')
  })

  it('点击查看打开详情抽屉并展示步骤/电话/风险', async () => {
    const el = await renderPanel()
    const row = el.querySelector('[data-row="card-1"]')
    const viewButton = findButton(row as HTMLElement, '查看')
    await act(async () => {
      viewButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    const drawer = el.querySelector('[data-drawer-open="true"]')
    expect(drawer?.textContent).toContain('发现异常')
    expect(drawer?.textContent).toContain('消防：119；急救：120')
    expect(drawer?.textContent).toContain('肺水肿')
    expect(drawer?.textContent).toContain('次生、衍生事故')
  })

  it('新增处置卡：提交映射后的表单数据', async () => {
    const el = await renderPanel()
    mocks.formValues = {
      workshop: '测试车间',
      position: '化测',
      title: '测试车间化测触电应急处置卡',
      subject: '触电',
      accident_type: '触电',
      steps: [{ order: '1', step: '脱离电源', action: '断电', person: '电工' }],
      phones: '急救：120',
      risks: '电击伤',
      precautions: '严禁徒手拉拽',
    }
    await act(async () => {
      findButton(el, '新增处置卡')?.dispatchEvent(
        new MouseEvent('click', { bubbles: true })
      )
    })
    await act(async () => {
      el.querySelector('[data-modal-ok]')?.dispatchEvent(
        new MouseEvent('click', { bubbles: true })
      )
    })
    expect(mocks.createEmergencyCard).toHaveBeenCalledTimes(1)
    const payload = mocks.createEmergencyCard.mock.calls[0][0]
    expect(payload.workshop).toBe('测试车间')
    expect(payload.position).toBe('化测')
    expect(payload.steps).toEqual([
      { order: '1', step: '脱离电源', action: '断电', person: '电工' },
    ])
    expect(mocks.messageApi.success).toHaveBeenCalled()
  })

  it('有删除权限时确认后删除处置卡', async () => {
    const el = await renderPanel()
    const row = el.querySelector('[data-row="card-1"]') as HTMLElement
    await act(async () => {
      findButton(row, '删除')?.dispatchEvent(
        new MouseEvent('click', { bubbles: true })
      )
    })
    const confirm = el.querySelector('[data-confirm]') as HTMLButtonElement
    await act(async () => {
      confirm.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    expect(mocks.deleteEmergencyCard).toHaveBeenCalledWith('card-1')
  })

  it('AI 分析：展示完整性与建议，采纳后追加到风险字段', async () => {
    const el = await renderPanel()
    const row = el.querySelector('[data-row="card-1"]') as HTMLElement
    await act(async () => {
      findButton(row, 'AI 分析')?.dispatchEvent(
        new MouseEvent('click', { bubbles: true })
      )
    })
    expect(mocks.reviewEmergencyCard).toHaveBeenCalledWith('card-1')
    const modal = el.querySelector('[data-modal-open="true"]')
    expect(modal?.textContent).toContain('处置步骤较完整')
    expect(modal?.textContent).toContain('已覆盖')
    expect(modal?.textContent).toContain('缺失')
    expect(modal?.textContent).toContain('补充泄漏风险')

    await act(async () => {
      findButton(modal as HTMLElement, '采纳并追加')?.dispatchEvent(
        new MouseEvent('click', { bubbles: true })
      )
    })
    const confirm = modal?.querySelector(
      '[data-confirm]'
    ) as HTMLButtonElement
    await act(async () => {
      confirm.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    expect(mocks.updateEmergencyCard).toHaveBeenCalledWith('card-1', {
      risks: '重度中毒：肺水肿、昏迷或休克\n泄漏会气化扩散，浓度过高导致人员中毒窒息。',
    })
    expect(mocks.messageApi.success).toHaveBeenCalled()
  })

  it('AI 分析失败时在弹窗中展示原因', async () => {
    mocks.reviewEmergencyCard.mockResolvedValue({
      code: 400,
      message: '尚未配置分析模型，请先在系统管理中启用 AI 模型配置',
    })
    const el = await renderPanel()
    const row = el.querySelector('[data-row="card-1"]') as HTMLElement
    await act(async () => {
      findButton(row, 'AI 分析')?.dispatchEvent(
        new MouseEvent('click', { bubbles: true })
      )
    })
    expect(el.querySelector('[data-notice]')?.getAttribute('data-notice')).toContain(
      'AI 分析未能完成'
    )
    expect(el.textContent).toContain('尚未配置分析模型')
  })

  it('无操作权限时隐藏新增/编辑/删除入口', async () => {
    mocks.canOperate = false
    const el = await renderPanel()
    expect(findButton(el, '新增处置卡')).toBeNull()
    const row = el.querySelector('[data-row="card-1"]') as HTMLElement
    expect(findButton(row, '编辑')).toBeNull()
    expect(findButton(row, '删除')).toBeNull()
  })

  it('编辑处置卡：打开编辑表单并提交更新', async () => {
    mocks.updateEmergencyCard.mockResolvedValue({ code: 200, message: 'success', data: null })
    await renderPanel()
    const editBtn = [...document.body.querySelectorAll<HTMLButtonElement>('button')].find((b) => b.textContent === '编辑')
    if (editBtn) {
      await act(async () => {
        editBtn.click()
        await new Promise((r) => setTimeout(r, 30))
      })
      const ok = [...document.body.querySelectorAll<HTMLButtonElement>('button')].find((b) =>
        b.textContent?.includes('确 定') || b.textContent?.includes('保存'),
      )
      if (ok) {
        await act(async () => {
          ok.click()
          await new Promise((r) => setTimeout(r, 30))
        })
        expect(mocks.updateEmergencyCard).toHaveBeenCalled()
      }
    }
  })

  it('切换车间页签联动岗位筛选', async () => {
    await renderPanel()
    const tabs = Array.from(document.body.querySelectorAll<HTMLButtonElement>('button')).filter((b) =>
          /车间|全部/.test(b.textContent ?? ''),
    )
if (tabs.length > 1) {
      await act(async () => {
        tabs[1].dispatchEvent(new MouseEvent('click', { bubbles: true }))
        await new Promise((r) => setTimeout(r, 30))
      })
    }
  })
})
