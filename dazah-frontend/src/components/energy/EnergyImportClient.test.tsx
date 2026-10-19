/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App, ConfigProvider, theme } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('@tanstack/react-query', () => ({ useQuery: () => ({ data: [], isLoading: false }) }))
vi.mock('@/actions/energy-ledger', () => ({ previewLedgerImport: vi.fn(), confirmLedgerImport: vi.fn(), createLedgerTemplateDraft: vi.fn(), previewLedgerSnapshots: vi.fn() }))

import { previewLedgerImport, confirmLedgerImport, createLedgerTemplateDraft } from '@/actions/energy-ledger'
import type { Meter, ImportPreview } from '@/lib/api/energy-ledger'
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
const changed = vi.fn(async () => undefined)
async function render(dark: boolean, meters: Meter[] = []) {
  const node = document.createElement('div'); document.body.append(node)
  root = createRoot(node)
  await act(async () => root?.render(<ConfigProvider locale={zhCN} theme={{ algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm }}><App><EnergyImportClient meters={meters} rules={[]} onChanged={changed} /></App></ConfigProvider>))
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

const mappedMeter: Meter = { id: 'meter-1', version: 1, definition: {
  code: 'water', name: '已核对水表', category: 'drinking_water', area: '101', department: '101车间', unit: 'm3', active_from: '2026-07-01',
  enabled: true, frequency: 'daily', multiplier: '1', precision: 3, reading_type: 'counter', report_scope: 'source', quantity_kind: 'volume',
  source_sheet: '饮用水码', source_column: 2, notes: '', temperature: '', workshop: '',
} }
const importedPreview: ImportPreview = { id: 'batch-1', status: 'preview', payload: { sheets: [
  { name: '饮用水码', category: 'drinking_water', headers: ['日期', '101车间'], input_columns: [2], cells: [{ column: 2, date: '2026-07-01', value: '12' }] },
], formulas: [], notes: ['请核对单位与倍率'] } }
async function clickImport(label: string, scope: ParentNode = document) {
  const button = [...scope.querySelectorAll<HTMLButtonElement>('button')].find(node => node.textContent?.replace(/\s/g, '') === label)
  expect(button, label).toBeDefined()
  await act(async () => button!.click())
}
async function importReason() {
  const field = document.querySelector<HTMLTextAreaElement>('textarea[aria-label="历史导入原因"]')!
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set?.call(field, '原表人工复核')
    field.dispatchEvent(new Event('input', { bubbles: true })); field.dispatchEvent(new Event('change', { bubbles: true }))
  })
}
it('requires an explicit mapping and reason and never writes before the confirmation', async () => {
  vi.mocked(previewLedgerImport).mockResolvedValue({ ok: true, data: importedPreview })
  await render(false); await clickImport('预览文件'); await importReason()
  await clickImport('确认导入已映射数据')
  expect(confirmLedgerImport).not.toHaveBeenCalled()
  await clickImport('确定', document.querySelector('[role=dialog]')!)
  expect(document.body.textContent).toContain('请选择至少一个计量点映射并填写导入原因')
  expect(confirmLedgerImport).not.toHaveBeenCalled()
})
it('retains a mapped import after a conflict and refreshes only after a successful retry', async () => {
  vi.mocked(previewLedgerImport).mockResolvedValue({ ok: true, data: importedPreview })
  vi.mocked(confirmLedgerImport).mockResolvedValueOnce({ ok: false, message: '已有新填报数据，整批停止' })
    .mockResolvedValueOnce({ ok: true, data: { ...importedPreview, status: 'imported' } })
  await render(false, [mappedMeter]); await clickImport('预览文件'); await importReason()
  expect(document.body.textContent).toContain('已核对水表')
  await clickImport('确认导入已映射数据'); await clickImport('确定', document.querySelector('[role=dialog]')!)
  expect(confirmLedgerImport).toHaveBeenCalledWith('batch-1', { mappings: [{ sheet: '饮用水码', column: 2, point_id: 'meter-1' }], reason: '原表人工复核', adjustments: [] })
  expect(document.body.textContent).toContain('已有新填报数据，整批停止')
  expect(changed).not.toHaveBeenCalled()
  await clickImport('确认导入已映射数据')
  await clickImport('确定', document.querySelector('[role=dialog]')!)
  expect(changed).toHaveBeenCalledOnce()
  expect(document.body.textContent).toContain('状态：已导入')
})
it('generates disabled configuration drafts only after confirmation and exposes review issues', async () => {
  vi.mocked(previewLedgerImport).mockResolvedValue({ ok: true, data: importedPreview })
  vi.mocked(createLedgerTemplateDraft).mockResolvedValue({ ok: true, data: { meters: [], rules: [], issues: ['需要确认共享倍率'] } })
  await render(false); await clickImport('预览文件'); await clickImport('生成计量与计算配置草案')
  expect(createLedgerTemplateDraft).not.toHaveBeenCalled()
  await clickImport('确定', document.querySelector('[role=dialog]')!)
  expect(createLedgerTemplateDraft).toHaveBeenCalledWith('batch-1')
  expect(changed).toHaveBeenCalledOnce()
  expect(document.body.textContent).toContain('需要确认共享倍率')
})
it('leaves the source file intact when draft configuration generation fails', async () => {
  vi.mocked(previewLedgerImport).mockResolvedValue({ ok: true, data: importedPreview })
  vi.mocked(createLedgerTemplateDraft).mockResolvedValue({ ok: false, message: '模板公式尚未核对' })
  await render(false); await clickImport('预览文件'); await clickImport('生成计量与计算配置草案')
  await clickImport('确定', document.querySelector('[role=dialog]')!)
  expect(document.body.textContent).toContain('模板公式尚未核对')
  expect(input('选择能源 Excel').files?.[0]?.name).toBe('energy.xlsx')
  expect(changed).not.toHaveBeenCalled()
})
