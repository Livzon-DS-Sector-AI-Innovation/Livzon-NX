/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const actions = vi.hoisted(() => ({ previewChangeImport: vi.fn(), confirmChangeImport: vi.fn() }))
vi.mock('@/actions/quality-import', () => actions)
import { ChangeImportDrawer } from './ChangeImportDrawer'

let container: HTMLElement
let root: Root
const onClose = vi.fn()
const onSuccess = vi.fn()

beforeEach(() => {
  vi.clearAllMocks()
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  act(() => root.render(<ChangeImportDrawer isOpen onClose={onClose} onSuccess={onSuccess} changeType="file" />))
  const input = container.querySelector('input[type=file]') as HTMLInputElement
  Object.defineProperty(input, 'files', { configurable: true, value: [new File(['docx'], 'import.docx')] })
  act(() => input.dispatchEvent(new Event('change', { bubbles: true })))
})
afterEach(() => { act(() => root.unmount()); container.remove(); vi.useRealTimers() })

async function click(label: string) {
  const button = Array.from(container.querySelectorAll('button')).find(item => item.textContent === label)
  expect(button).toBeDefined()
  await act(async () => button?.dispatchEvent(new MouseEvent('click', { bubbles: true })))
}
async function preview() {
  actions.previewChangeImport.mockResolvedValue({ ok: true, data: { total_rows: 2, valid_rows: 2, error_rows: [] } })
  await click('预览数据')
  expect(actions.previewChangeImport).toHaveBeenCalledWith(expect.any(FormData), 'file')
}

it('shows public authorization errors and preserves the selected document', async () => {
  await preview()
  actions.confirmChangeImport.mockResolvedValue({ ok: false, message: '未获得当前高风险业务动作授权' })
  await click('确认导入')
  expect(container.textContent).toContain('未获得当前高风险业务动作授权')
  expect(container.textContent).toContain('import.docx')
  expect(container.textContent).not.toContain('React error')
  expect(onSuccess).not.toHaveBeenCalled()
  expect(onClose).not.toHaveBeenCalled()
})

it('keeps partial failures open, displays row details and refreshes saved rows', async () => {
  await preview()
  actions.confirmChangeImport.mockResolvedValue({ ok: true, data: { success_count: 1, update_count: 0, skip_count: 0, error_count: 1,
    error_details: [{ row: 3, error: '变更对象不能超过255个字符' }] } })
  await click('确认导入')
  expect(container.textContent).toContain('第3行：变更对象不能超过255个字符')
  expect(container.textContent).toContain('已成功的数据已保存')
  expect(onSuccess).toHaveBeenCalledOnce()
  expect(onClose).not.toHaveBeenCalled()
  expect(Array.from(container.querySelectorAll('button')).some(button => button.textContent === '确认导入')).toBe(false)
})

it('closes and refreshes after a fully successful import', async () => {
  await preview()
  vi.useFakeTimers()
  actions.confirmChangeImport.mockResolvedValue({ ok: true, data: { success_count: 2, update_count: 0, skip_count: 0, error_count: 0 } })
  await click('确认导入')
  expect(actions.confirmChangeImport).toHaveBeenCalledWith(expect.any(FormData), true, false, 'file')
  expect(container.textContent).toContain('2 条成功')
  act(() => vi.advanceTimersByTime(1500))
  expect(onClose).toHaveBeenCalledOnce()
  expect(onSuccess).toHaveBeenCalledOnce()
})
