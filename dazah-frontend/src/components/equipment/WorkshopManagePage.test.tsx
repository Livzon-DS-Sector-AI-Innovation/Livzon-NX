/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App as AntApp } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  fetchAllEquipmentWorkshops: vi.fn(),
  createEquipmentWorkshop: vi.fn(),
  updateEquipmentWorkshop: vi.fn(),
}))

const registry = vi.hoisted(() => ({
  invalidateEquipmentWorkshops: vi.fn(),
  loadEquipmentWorkshops: vi.fn(async () => []),
  useEquipmentWorkshops: () => [],
}))

vi.mock('@/lib/api/equipment-workshops', () => api)
vi.mock('@/lib/equipment-workshop-registry', () => registry)

import { WorkshopManagePage } from './WorkshopManagePage'

const rowsFixture = [
  {
    code: '101-1',
    name: '101一车间',
    is_enabled: true,
    created_at: '2026-10-01T00:00:00Z',
  },
  {
    code: '204',
    name: '204车间',
    is_enabled: false,
    created_at: '2026-10-20T00:00:00Z',
  },
]

let root: Root | null = null

beforeEach(() => {
  vi.clearAllMocks()
  api.fetchAllEquipmentWorkshops.mockResolvedValue(rowsFixture)
})

afterEach(() => {
  act(() => root?.unmount())
  document.body.innerHTML = ''
})

async function renderPage() {
  const container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  await act(async () => {
    root!.render(<AntApp><WorkshopManagePage /></AntApp>)
  })
  await act(async () => { await new Promise((r) => setTimeout(r, 40)) })
}

function rowOf(code: string): HTMLTableRowElement | undefined {
  return Array.from(document.querySelectorAll('tr'))
    .find((tr) => tr.textContent?.includes(code)) as HTMLTableRowElement | undefined
}

function findButtonByText(text: string, notInTable = false): HTMLButtonElement {
  const target = Array.from(document.querySelectorAll('button'))
    .find((b) => (b.textContent || '').replace(/\s/g, '') === text
      && (!notInTable || !b.closest('table')))
  if (!target) throw new Error(`button not found: ${text}`)
  return target
}

/** React 会跟踪 value setter 去重 input 事件，需用原型原生 setter 赋值 */
function setInputValue(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(
    HTMLInputElement.prototype,
    'value',
  )?.set
  setter?.call(input, value)
  input.dispatchEvent(new Event('input', { bubbles: true }))
}

describe('WorkshopManagePage（车间管理页）', () => {
  it('渲染车间清单：启用/停用状态与登记时间', async () => {
    await renderPage()
    const row101 = rowOf('101-1')!
    expect(row101.textContent).toContain('101一车间')
    expect(row101.textContent).toContain('启用')
    const row204 = rowOf('204')!
    expect(row204.textContent).toContain('停用')
    expect(document.body.textContent).toContain('新增车间')
  })

  it('新增车间：填代码与名称后提交并调用创建接口', async () => {
    api.createEquipmentWorkshop.mockResolvedValue(rowsFixture[0])
    await renderPage()
    await act(async () => { findButtonByText('新增车间').click() })
    await act(async () => { await new Promise((r) => setTimeout(r, 40)) })

    const codeInput = document.querySelector('input[placeholder="204 / 204-1 / dlz"]') as HTMLInputElement
    const nameInput = document.querySelector('input[placeholder="如：204一车间"]') as HTMLInputElement
    expect(codeInput).toBeTruthy()
    await act(async () => {
      setInputValue(codeInput, '204-1')
      setInputValue(nameInput, '204一车间')
    })
    await act(async () => { findButtonByText('新增', true).click() })
    await act(async () => { await new Promise((r) => setTimeout(r, 40)) })

    expect(api.createEquipmentWorkshop).toHaveBeenCalledWith({
      code: '204-1',
      name: '204一车间',
    })
    // 保存后让其他入口的缓存失效
    expect(registry.invalidateEquipmentWorkshops).toHaveBeenCalled()
  })

  it('新增失败（代码重复）时展示后端错误信息', async () => {
    api.createEquipmentWorkshop.mockRejectedValue(
      new Error('车间代码 204 已存在（204车间），请换一个代码'),
    )
    await renderPage()
    await act(async () => { findButtonByText('新增车间').click() })
    await act(async () => { await new Promise((r) => setTimeout(r, 40)) })
    const codeInput = document.querySelector('input[placeholder="204 / 204-1 / dlz"]') as HTMLInputElement
    const nameInput = document.querySelector('input[placeholder="如：204一车间"]') as HTMLInputElement
    await act(async () => {
      setInputValue(codeInput, '204')
      setInputValue(nameInput, '重复车间')
    })
    await act(async () => { findButtonByText('新增', true).click() })
    await act(async () => { await new Promise((r) => setTimeout(r, 40)) })

    expect(document.body.textContent).toContain('已存在')
  })

  it('改名车间：弹窗预填并提交新名称', async () => {
    api.updateEquipmentWorkshop.mockResolvedValue({ ...rowsFixture[0], name: '101新一车间' })
    await renderPage()
    const row101 = rowOf('101-1')!
    const renameBtn = row101.querySelector('button[aria-label="改名车间 101一车间"]') as HTMLButtonElement
    await act(async () => { renameBtn.click() })
    await act(async () => { await new Promise((r) => setTimeout(r, 40)) })

    const nameInput = document.querySelector('input[placeholder="如：204一车间"]') as HTMLInputElement
    expect((nameInput as HTMLInputElement).value).toBe('101一车间')
    // 代码输入框在改名模式下禁用
    const codeInput = document.querySelector('input[placeholder="204 / 204-1 / dlz"]') as HTMLInputElement
    expect(codeInput.disabled).toBe(true)
    await act(async () => { setInputValue(nameInput, '101新一车间') })
    await act(async () => { findButtonByText('保存', true).click() })
    await act(async () => { await new Promise((r) => setTimeout(r, 40)) })

    expect(api.updateEquipmentWorkshop).toHaveBeenCalledWith('101-1', {
      name: '101新一车间',
    })
  })

  it('停用车间需二次确认，确认后调用启停接口', async () => {
    api.updateEquipmentWorkshop.mockResolvedValue({ ...rowsFixture[0], is_enabled: false })
    await renderPage()
    const row101 = rowOf('101-1')!
    const stopBtn = row101.querySelector('button[aria-label="停用车间 101一车间"]') as HTMLButtonElement
    await act(async () => { stopBtn.click() })
    await act(async () => { await new Promise((r) => setTimeout(r, 40)) })

    const confirmBtn = findButtonByText('停用', true)
    await act(async () => { confirmBtn.click() })
    await act(async () => { await new Promise((r) => setTimeout(r, 40)) })

    expect(api.updateEquipmentWorkshop).toHaveBeenCalledWith('101-1', {
      is_enabled: false,
    })
  })

  it('绑定群：弹窗预填会话 ID 并提交绑定', async () => {
    api.updateEquipmentWorkshop.mockResolvedValue({ ...rowsFixture[0] })
    await renderPage()
    const row101 = rowOf('101-1')!
    const bindBtn = row101.querySelector('button[aria-label="绑定群 101一车间"]') as HTMLButtonElement
    expect(bindBtn).toBeTruthy()
    await act(async () => { bindBtn.click() })
    await act(async () => { await new Promise((r) => setTimeout(r, 40)) })

    const input = document.querySelector('input[placeholder="oc_ 开头的会话 ID"]') as HTMLInputElement
    expect(input).toBeTruthy()
    await act(async () => { setInputValue(input, 'oc_chat_101') })
    await act(async () => { findButtonByText('保存', true).click() })
    await act(async () => { await new Promise((r) => setTimeout(r, 40)) })

    expect(api.updateEquipmentWorkshop).toHaveBeenCalledWith('101-1', {
      feishu_chat_id: 'oc_chat_101',
    })
  })
})
