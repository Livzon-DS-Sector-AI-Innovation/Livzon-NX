/* @vitest-environment happy-dom */
import { act, createElement, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })

const mocks = vi.hoisted(() => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  createEmergencyPlan: vi.fn(),
  submitEmergencyPlanGenerate: vi.fn(),
  importEmergencyPlanDocx: vi.fn(),
  fetchEmergencyPlanAiOptions: vi.fn(async () => ({
    code: 200,
    data: {
      chemicals: [
        { id: 'c1', name: '乙醇', cas_no: '64-17-5', category: '易燃液体', has_msds: true },
      ],
      buildings: [{ code: 'B1', name: '危险品库', category: 'warehouse' }],
      accident_types: [
        { value: 'fire', label: '火灾' },
        { value: 'leak_fire', label: '泄漏火灾' },
      ],
      levels: [
        { value: 'company', label: '公司级' },
        { value: 'workshop', label: '车间级' },
      ],
      default_company: '丽珠集团（宁夏）制药有限公司',
      default_organization: {
        commander: '',
        commander_duties: '',
        deputy_commanders: [],
        deputy_duties: '',
        groups: [],
      },
      default_workshop_organization: {
        department: '',
        commander: '',
        deputy_commander: '',
        groups: [],
      },
      recent_organization: {
        commander: '史润',
        commander_duties: '',
        deputy_commanders: ['田成'],
        deputy_duties: '',
        groups: [{ name: '应急处置组', leader: '朱少军', members: '', duties: '' }],
      },
      recent_workshop_organization: null,
    },
  })),
}))

vi.mock('@/actions/safety', () => ({
  createEmergencyPlan: mocks.createEmergencyPlan,
  submitEmergencyPlanGenerate: mocks.submitEmergencyPlanGenerate,
  importEmergencyPlanDocx: mocks.importEmergencyPlanDocx,
  fetchEmergencyPlanAiOptions: mocks.fetchEmergencyPlanAiOptions,
}))

vi.mock('@ant-design/icons', () => {
  const Icon = () => null
  return { ThunderboltOutlined: Icon, UploadOutlined: Icon }
})

vi.mock('antd', async () => {
  const { createElement } = await import('react')
  type AnyProps = Record<string, unknown>
  const Box = ({ children }: AnyProps) =>
    createElement('div', null, children as ReactNode)
  const Button = ({ children, onClick, disabled }: AnyProps) =>
    createElement(
      'button',
      { type: 'button', disabled: Boolean(disabled), onClick: onClick as never },
      children as ReactNode
    )
  const Input = Object.assign(
    ({ value, onChange, placeholder }: AnyProps) =>
      createElement('input', {
        value: (value as string) ?? '',
        placeholder: placeholder as string | undefined,
        onChange: (event: { target: { value: string } }) =>
          (onChange as ((event: { target: { value: string } }) => void) | undefined)?.({ target: { value: event.target.value } }),
      }),
    { TextArea: ({ value }: AnyProps) => createElement('textarea', { value: (value as string) ?? '' }) }
  )
  const Modal = ({ children, open, footer, title }: AnyProps) =>
    createElement(
      'div',
      { 'data-modal-open': String(Boolean(open)) },
      open
        ? [
            createElement('h3', { key: 't' }, title as ReactNode),
            children as ReactNode,
            createElement(
              'div',
              { key: 'f', 'data-modal-footer': 'y' },
              footer as ReactNode
            ),
          ]
        : null
    )
  const Steps = ({ items }: { items?: Array<{ title: string }> }) =>
    createElement(
      'div',
      null,
      (items ?? []).map((item) =>
        createElement('span', { key: item.title, 'data-step': item.title }, item.title)
      )
    )
  return {
    App: Object.assign(Box, { useApp: () => ({ message: mocks.message }) }),
    Button,
    DatePicker: () => createElement('input'),
    Form: Object.assign(Box, {
      Item: ({ children, label }: AnyProps) =>
        createElement(
          'div',
          null,
          label ? createElement('span', null, label as ReactNode) : null,
          children as ReactNode
        ),
    }),
    Input,
    Modal,
    Select: ({
      value,
      options,
      onChange,
    }: AnyProps) =>
      createElement(
        'select',
        {
          value: (value as string) ?? '',
          onChange: (event: { target: { value: string } }) =>
            (onChange as ((value: string) => void) | undefined)?.(event.target.value),
        },
        ((options as Array<{ value: string; label: string }> | undefined) ?? []).map((option) =>
          createElement('option', { key: option.value, value: option.value }, option.label)
        )
      ),
    Space: Object.assign(Box, { Compact: Box }),
    Steps,
    Tag: ({ children }: AnyProps) => createElement('span', null, children as ReactNode),
    Upload: ({ children }: AnyProps) => createElement('span', null, children as ReactNode),
  }
})

import EmergencyPlanGenerateModal from './EmergencyPlanGenerateModal'

let container: HTMLDivElement
let root: Root | null = null

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  vi.clearAllMocks()
})

afterEach(() => {
  root?.unmount()
  container.remove()
  root = null
})

async function renderModal(mode: 'generate' | 'import', onCreated = vi.fn()) {
  root = createRoot(container)
  await act(async () => {
    root!.render(
      createElement(EmergencyPlanGenerateModal, {
        open: true,
        mode,
        onClose: vi.fn(),
        onCreated,
      })
    )
    await new Promise((resolve) => setTimeout(resolve, 30))
  })
  return onCreated
}

function setNativeValue(
  element: HTMLInputElement | HTMLSelectElement,
  value: string,
  eventName: 'input' | 'change' = 'input'
) {
  const prototype =
    element instanceof HTMLSelectElement
      ? HTMLSelectElement.prototype
      : HTMLInputElement.prototype
  Object.getOwnPropertyDescriptor(prototype, 'value')?.set?.call(element, value)
  element.dispatchEvent(new Event(eventName, { bubbles: true }))
}

function findButtonAll(text: string) {
  return [...container.querySelectorAll<HTMLButtonElement>('button')].filter(
    (button) => button.textContent?.includes(text)
  )
}

function flush(ms = 30) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function findButton(text: string) {
  return [...container.querySelectorAll<HTMLButtonElement>('button')].find(
    (button) => button.textContent?.includes(text)
  )
}

describe('EmergencyPlanGenerateModal', () => {
  it('第一步渲染基本信息与预填的组织机构人名', async () => {
    await renderModal('generate')
    expect(container.innerHTML).toContain('AI 生成应急预案')
    // 单选级别默认公司级（通过 select 值判断）
    const levelSelect = [...container.querySelectorAll('select')][0]
    expect(levelSelect?.value).toBe('company')
  })

  it('向导四步走完提交生成任务并回调 planId', async () => {
    const onCreated = await renderModal('generate')
    mocks.createEmergencyPlan.mockResolvedValue({
      code: 200,
      data: { id: 'plan-9' },
    })
    mocks.submitEmergencyPlanGenerate.mockResolvedValue({
      code: 200,
      data: { job_id: 'job-1', kind: 'generate' },
    })
    // 第一步：填名称、选事故类型
    const nameInput = [...container.querySelectorAll<HTMLInputElement>('input')][0]
    await act(async () => {
      setNativeValue(nameInput!, '危险品库乙醇火灾事故综合应急演练方案')
    })
    const accidentSelect = [...container.querySelectorAll('select')][1]
    await act(async () => {
      setNativeValue(accidentSelect!, 'leak_fire', 'change')
    })
    await act(async () => {
      findButton('下一步')!.click()
      await new Promise((resolve) => setTimeout(resolve, 10))
    })
    // 第二步：填场所
    const locationInput = [...container.querySelectorAll<HTMLInputElement>('input')][0]
    await act(async () => {
      setNativeValue(locationInput!, '危险品库')
    })
    await act(async () => {
      findButton('下一步')!.click()
      await new Promise((resolve) => setTimeout(resolve, 10))
    })
    // 第三步：组织机构（已预填史润/朱少军）
    expect(container.innerHTML).toContain('应急处置组')
    await act(async () => {
      findButton('下一步')!.click()
      await new Promise((resolve) => setTimeout(resolve, 10))
    })
    // 第四步：确认生成
    const submit = findButton('创建并开始 AI 生成')
    expect(submit).toBeDefined()
    await act(async () => {
      submit!.click()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    expect(mocks.createEmergencyPlan).toHaveBeenCalledWith(
      expect.objectContaining({ name: '危险品库乙醇火灾事故综合应急演练方案' })
    )
    expect(mocks.submitEmergencyPlanGenerate).toHaveBeenCalledWith(
      'plan-9',
      expect.objectContaining({
        location: '危险品库',
        accident_type: 'leak_fire',
        // 组织机构人名按最近一次公司级预案预填
        organization: expect.objectContaining({
          commander: '史润',
          deputy_commanders: ['田成'],
        }),
      })
    )
    expect(onCreated).toHaveBeenCalledWith('plan-9')
  })

  it('import 模式未选文件时提示并阻断提交', async () => {
    const onCreated = await renderModal('import')
    await act(async () => {
      findButton('下一步')!.click()
      await new Promise((resolve) => setTimeout(resolve, 10))
    })
    const submit = findButton('创建并导入')
    await act(async () => {
      submit!.click()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    expect(mocks.message.warning).toHaveBeenCalled()
    expect(mocks.createEmergencyPlan).not.toHaveBeenCalled()
    expect(onCreated).not.toHaveBeenCalled()
  })
})

describe('EmergencyPlanGenerateModal：错误分支与 import 流程', () => {
  async function driveGenerate(onCreated: ReturnType<typeof vi.fn>) {
    const nameInput = [...container.querySelectorAll<HTMLInputElement>('input')][0]
    await act(async () => {
      setNativeValue(nameInput!, '危险品库乙醇火灾演练方案')
    })
    const accidentSelect = [...container.querySelectorAll('select')][1]
    await act(async () => {
      setNativeValue(accidentSelect!, 'leak_fire', 'change')
    })
    await act(async () => {
      findButton('下一步')!.click()
      await new Promise((resolve) => setTimeout(resolve, 10))
    })
    const locationInput = [...container.querySelectorAll<HTMLInputElement>('input')][0]
    await act(async () => {
      setNativeValue(locationInput!, '危险品库')
    })
    await act(async () => {
      findButton('下一步')!.click()
      await new Promise((resolve) => setTimeout(resolve, 10))
    })
    await act(async () => {
      findButton('下一步')!.click()
      await new Promise((resolve) => setTimeout(resolve, 10))
    })
    const submit = findButton('创建并开始 AI 生成')
    expect(submit).toBeDefined()
    await act(async () => {
      submit!.click()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    return onCreated
  }

  it('创建预案失败提示并中止', async () => {
    const onCreated = await renderModal('generate')
    mocks.createEmergencyPlan.mockResolvedValue({
      code: 500,
      message: '名称重复',
    })
    await driveGenerate(onCreated)
    expect(mocks.createEmergencyPlan).toHaveBeenCalled()
    expect(mocks.message.error).toHaveBeenCalledWith('名称重复')
    expect(onCreated).not.toHaveBeenCalled()
  })

  it('提交生成任务失败提示', async () => {
    const onCreated = await renderModal('generate')
    mocks.createEmergencyPlan.mockResolvedValue({
      code: 200,
      data: { id: 'plan-new' },
    })
    mocks.submitEmergencyPlanGenerate.mockResolvedValue({
      code: 500,
      message: '模型不可用',
    })
    await driveGenerate(onCreated)
    expect(mocks.submitEmergencyPlanGenerate).toHaveBeenCalled()
    expect(mocks.message.error).toHaveBeenCalledWith('模型不可用')
    expect(onCreated).not.toHaveBeenCalled()
  })
})
