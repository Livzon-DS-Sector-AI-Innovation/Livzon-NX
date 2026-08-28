/* @vitest-environment happy-dom */
/**
 * 真实 antd 集成测试：不 mock antd，验证加急单表单在真实 Form/Table/
 * AutoComplete 行为下的金额计算与物料自动填入，用于复现线上行为。
 */
/* eslint-disable @typescript-eslint/no-explicit-any */

import { act, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from 'antd'
import { PurchaseRequestFormClient } from './PurchaseRequestFormClient'

const actions = vi.hoisted(() => ({
  createPurchaseRequest: vi.fn(),
  submitPurchaseRequest: vi.fn(),
  updatePurchaseRequest: vi.fn(),
}))

const api = vi.hoisted(() => ({
  fetchPurchaseRequests: vi.fn(),
  fetchMaterialOptions: vi.fn(),
}))

vi.mock('@/actions/purchasing', () => actions)
vi.mock('@/lib/api/purchasing', () => api)

function mockMatchMedia() {
  window.matchMedia = window.matchMedia ?? ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }))
}

function mockResizeObserver() {
  if (!(globalThis as any).ResizeObserver) {
    ;(globalThis as any).ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
  }
}

function setInputValue(element: HTMLInputElement | HTMLTextAreaElement | null, value: string) {
  if (!element) throw new Error('setInputValue: element not found')
  // 与 React Testing Library 一致：走原型 setter 绕过 React 的 value tracker，
  // 直接赋值不会触发受控组件的 onChange
  const prototype = element instanceof HTMLTextAreaElement
    ? window.HTMLTextAreaElement.prototype
    : window.HTMLInputElement.prototype
  const setter = Object.getOwnPropertyDescriptor(prototype, 'value')?.set
  setter?.call(element, value)
  element.dispatchEvent(new Event('input', { bubbles: true }))
}

let container: HTMLDivElement
let root: Root

async function render(element: ReactNode) {
  container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
  await act(async () => {
    root.render(element)
  })
}

// antd 会给两个汉字的按钮文本自动插入空格（"添 加"），匹配时忽略空白
function buttonByText(text: string) {
  return Array.from(document.body.querySelectorAll<HTMLButtonElement>('button')).find(
    (button) => button.textContent?.replace(/\s/g, '') === text,
  )
}

async function clickButton(text: string) {
  await act(async () => {
    buttonByText(text)?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  })
}

async function selectCategory(label: string) {
  // antd v6 Select：mousedown 打开下拉（v5 的 .ant-select-selector 已改为 .ant-select-content）
  await act(async () => {
    document.body
      .querySelector<HTMLElement>('.ant-select-content')
      ?.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
  })
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 50))
  })
  await act(async () => {
    const option = Array.from(
      document.body.querySelectorAll<HTMLElement>('.ant-select-item-option'),
    ).find((item) => item.textContent?.includes(label))
    option?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  })
}

async function addHardwareGroup() {
  await clickButton('添加申请类型')
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 50))
  })
  await selectCategory('五金材料')
  await clickButton('添加')
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 50))
  })
}

beforeAll(() => {
  mockMatchMedia()
  mockResizeObserver()
})

beforeEach(() => {
  vi.clearAllMocks()
  actions.createPurchaseRequest.mockResolvedValue({ code: 200, message: 'success', data: {} })
  actions.submitPurchaseRequest.mockResolvedValue({ code: 200, message: 'success', data: {} })
  actions.updatePurchaseRequest.mockResolvedValue({ code: 200, message: 'success', data: {} })
  api.fetchPurchaseRequests.mockResolvedValue({ code: 200, message: 'success', data: [], meta: { total: 0 } })
  window.scrollTo = vi.fn()
})

afterEach(() => {
  act(() => root?.unmount())
  container?.remove()
  document.body.innerHTML = ''
})

describe('urgent purchase request form with real antd', () => {
  it('computes line totals, group subtotals, and the grand total as the user types', async () => {
    await render(
      <App>
        <PurchaseRequestFormClient
          category="urgent"
          categoryLabel="加急单"
          initialRequests={[]}
          initialTotal={0}
        />
      </App>,
    )

    await addHardwareGroup()
    await clickButton('新增明细')

    const numberInputs = () => Array.from(
      document.body.querySelectorAll<HTMLInputElement>('input.ant-input-number-input'),
    )
    expect(numberInputs().length).toBe(4)
    // 第一行：数量 2 × 单价 5；第二行：数量 3 × 单价 5
    await act(async () => {
      const inputs = numberInputs()
      setInputValue(inputs[0], '2')
      setInputValue(inputs[1], '5')
      setInputValue(inputs[2], '3')
      setInputValue(inputs[3], '5')
    })

    const text = () => document.body.textContent ?? ''
    expect(text()).toContain('¥10.00')
    expect(text()).toContain('¥15.00')
    expect(text()).toContain('分组小计')
    expect(text()).toContain('合计：¥25.00')
  })

  it('auto-fills material description and rule model when the material code matches', async () => {
    api.fetchMaterialOptions.mockResolvedValue({
      code: 200,
      message: 'success',
      data: [{
        record_id: 'rec-1',
        material_code: 'MAT-001',
        material_description: '不锈钢管',
        rule_model: 'DN50',
        material_unit: '米',
      }],
    })

    await render(
      <App>
        <PurchaseRequestFormClient
          category="urgent"
          categoryLabel="加急单"
          initialRequests={[]}
          initialTotal={0}
        />
      </App>,
    )

    await addHardwareGroup()

    // antd v6 的 placeholder 渲染为独立元素，输入框本身无 placeholder 属性；
    // 物料编码 AutoComplete 输入框为可编辑的 .ant-select-input（分类下拉框的是 readonly）
    const materialCodeInput = document.body.querySelector<HTMLInputElement>(
      'input.ant-select-input:not([readonly])',
    )
    expect(materialCodeInput).not.toBeNull()
    await act(async () => {
      setInputValue(materialCodeInput, 'MAT-001')
    })
    // 等待联想防抖（180ms）与远端匹配完成
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 500))
    })

    const values = Array.from(
      document.body.querySelectorAll<HTMLInputElement>('input.ant-input'),
    ).map((input) => input.value)
    expect(values).toContain('不锈钢管')
    expect(values).toContain('DN50')
    // 物料编码输入框保持用户输入的值
    expect(materialCodeInput?.value).toBe('MAT-001')
  })
})
