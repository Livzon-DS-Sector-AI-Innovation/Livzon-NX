/* @vitest-environment happy-dom */

import { act, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { CapaImportDrawer } from './capa-import-drawer'
import { ChangeImportDrawer } from './change-import-drawer'
import { DeviationImportDrawer } from './deviation-import-drawer'

const requests = vi.hoisted(() => ({
  previewLegacyCapaImport: vi.fn(), confirmLegacyCapaImport: vi.fn(),
  previewLegacyChangeImport: vi.fn(), confirmLegacyChangeImport: vi.fn(),
  previewLegacyDeviationImport: vi.fn(), confirmLegacyDeviationImport: vi.fn(),
}))
vi.mock('@/actions/quality-import', () => requests)

let host: HTMLDivElement
let root: Root
const close = vi.fn()
const success = vi.fn()
const props = { isOpen: true, onClose: close, onSuccess: success }
const parserError = 'TypeError: internal Word parser error'

beforeEach(() => {
  vi.resetAllMocks()
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
})

afterEach(async () => {
  await act(async () => root.unmount())
  host.remove()
  vi.unstubAllGlobals()
})

async function render(element: ReactNode) {
  await act(async () => root.render(element))
}

async function click(label: string) {
  const button = Array.from(host.querySelectorAll('button')).find(el => el.textContent?.trim() === label)
  expect(button?.disabled).toBe(false)
  await act(async () => button?.click())
}

it.each([
  ['CAPA', CapaImportDrawer, 'previewLegacyCapaImport', 'confirmLegacyCapaImport'],
  ['变更', ChangeImportDrawer, 'previewLegacyChangeImport', 'confirmLegacyChangeImport'],
  ['偏差', DeviationImportDrawer, 'previewLegacyDeviationImport', 'confirmLegacyDeviationImport'],
] as const)('%s 导入在预览或确认失败时保留文件', async (_, Drawer, preview, confirm) => {
  requests[preview]
    .mockRejectedValueOnce(new Error(parserError))
    .mockResolvedValueOnce({ ok: true, data: { total_rows: 1, valid_rows: 1, error_rows: [] } })
  requests[confirm].mockRejectedValueOnce(new Error(parserError))
  await render(<Drawer {...props} />)
  const picker = host.querySelector<HTMLInputElement>('input[type=file]')
  expect(picker).not.toBeNull()
  Object.defineProperty(picker, 'files', { value: [new File(['test'], '示例.docx')] })
  await act(async () => picker?.dispatchEvent(new Event('change', { bubbles: true })))

  await click('预览数据')
  expect(host.textContent).toContain('预览失败')
  expect(host.textContent).toContain('示例.docx')
  expect(host.textContent).not.toContain(parserError)
  expect(requests[confirm]).not.toHaveBeenCalled()

  await click('预览数据')
  expect(host.textContent).toContain('可导入')
  await click('确认导入')
  expect(host.textContent).toContain('导入失败')
  expect(host.textContent).toContain('示例.docx')
  expect(host.textContent).not.toContain(parserError)
  expect(close).not.toHaveBeenCalled()
  expect(success).not.toHaveBeenCalled()
  expect(requests[confirm].mock.calls[0][0].get('file')).toHaveProperty('name', '示例.docx')
})

it('shows a recoverable error when the change import template cannot be downloaded', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 503 })))
  await render(<ChangeImportDrawer {...props} />)
  await click('下载导入模板（从系统导出）')

  expect(host.textContent).toContain('下载模板失败')
  expect(close).not.toHaveBeenCalled()
})
