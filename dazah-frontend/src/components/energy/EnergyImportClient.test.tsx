/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App, ConfigProvider, theme } from 'antd'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('@tanstack/react-query', () => ({ useQuery: () => ({ data: [], isLoading: false }) }))
vi.mock('@/actions/energy-ledger', () => ({ previewLedgerImport: vi.fn(), confirmLedgerImport: vi.fn(), createLedgerTemplateDraft: vi.fn(), previewLedgerSnapshots: vi.fn() }))

import { previewLedgerImport } from '@/actions/energy-ledger'
import { EnergyImportClient } from './EnergyImportClient'

let root: Root | undefined
afterEach(async () => { await act(async () => root?.unmount()); root = undefined; document.body.innerHTML = ''; vi.clearAllMocks() })

function input(label: string): HTMLInputElement {
  const element = document.querySelector<HTMLInputElement>(`input[aria-label="${label}"]`)
  if (!element) throw new Error(`Missing input: ${label}`)
  return element
}
function setDate(label: string, value: string) {
  const field = input(label)
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(field, value)
  field.dispatchEvent(new Event('input', { bubbles: true }))
  field.dispatchEvent(new Event('change', { bubbles: true }))
}
async function render(dark: boolean) {
  const node = document.createElement('div'); document.body.append(node)
  root = createRoot(node)
  await act(async () => root?.render(<ConfigProvider theme={{ algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm }}><App><EnergyImportClient meters={[]} rules={[]} onChanged={async () => undefined} /></App></ConfigProvider>))
  const picker = input('选择能源 Excel')
  Object.defineProperty(picker, 'files', { value: [new File(['data'], 'energy.xlsx')] })
  await act(async () => picker.dispatchEvent(new Event('change', { bubbles: true })))
}

describe('energy import preview flow', () => {
  it.each([false, true])('keeps the selected period explicit and invalidates stale previews (dark=%s)', async dark => {
    vi.mocked(previewLedgerImport).mockResolvedValue({ ok: true, data: { id: 'batch', status: 'preview', payload: { start_date: '2026-06-27', end_date: '2026-07-19', sheets: [], formulas: [] } } })
    await render(dark)
    await act(async () => { setDate('有效开始日期', '2026-06-27'); setDate('有效结束日期', '2026-07-19') })
    const button = Array.from(document.querySelectorAll('button')).find(item => item.textContent === '预览文件')
    await act(async () => button?.click())
    const data = vi.mocked(previewLedgerImport).mock.calls[0]?.[0]
    expect(data?.get('start_date')).toBe('2026-06-27')
    expect(data?.get('end_date')).toBe('2026-07-19')
    expect(document.body.textContent).toContain('有效范围 2026-06-27 至 2026-07-19')
    expect(document.querySelector<HTMLElement>('[data-platform-notice]')?.style.background).toBeTruthy()
    await act(async () => setDate('有效结束日期', '2026-07-18'))
    expect(document.body.textContent).not.toContain('生成计量与计算配置草案')
  })
  it('preserves the selected file and shows a failed preview without offering confirmation', async () => {
    vi.mocked(previewLedgerImport).mockResolvedValue({ ok: false, message: '文件不是有效工作簿' })
    await render(false)
    const button = Array.from(document.querySelectorAll('button')).find(item => item.textContent === '预览文件')
    await act(async () => button?.click())
    expect(document.body.textContent).toContain('文件不是有效工作簿')
    expect(input('选择能源 Excel').files?.[0]?.name).toBe('energy.xlsx')
    expect(document.body.textContent).not.toContain('确认导入已映射数据')
  })
})
