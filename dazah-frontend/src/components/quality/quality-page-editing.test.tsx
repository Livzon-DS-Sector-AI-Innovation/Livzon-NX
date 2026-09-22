/* @vitest-environment happy-dom */
/* @vitest-environment-options {"settings":{"disableIframePageLoading":true,"handleDisabledFileLoadingAsSuccess":true}} */
import React, { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App, ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ report: vi.fn(), investigation: vi.fn(), capa: vi.fn(), createPlan: vi.fn(), saveDetail: vi.fn(), product: vi.fn(), fetch: vi.fn() }))
vi.mock('next/navigation', () => ({ useSearchParams: () => new URLSearchParams(), useParams: () => ({ id: 'capa' }), useRouter: () => ({ push: vi.fn() }) }))
vi.mock('next/link', () => ({ default: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a> }))
vi.mock('@/actions/quality', () => ({
  updateOosOotReportRecord: mocks.report, updateOosOotInvestigationPushRecord: mocks.investigation,
  pullOosOotReportRecords: vi.fn(), deleteOosOotReportRecord: vi.fn(),
  pullOosOotInvestigationPushRecords: vi.fn(), deleteOosOotInvestigationPushRecord: vi.fn(),
  updateProductDepartmentRecord: mocks.product, createProductDepartmentRecord: vi.fn(),
  pullProductDepartmentRecords: vi.fn(), deleteProductDepartmentRecord: vi.fn(),
}))
vi.mock('@/actions/quality-capa', () => ({ updateCapaPlanTrack: mocks.capa, createCapaPlanTrack: mocks.createPlan, updateCapa: mocks.saveDetail, deleteCapaPlanTrack: vi.fn(), syncCapaPlanTracksFromFeishu: vi.fn() }))
vi.mock('@/lib/api/client/quality', () => ({
  fetchQualityFeishuAppSettings: async () => ({}),
  fetchQualityPersonDirectory: async () => [
    { name: '原人员', open_id: 'ou_old', department: 'QC' },
    { name: '新人员', open_id: 'ou_new', department: 'QC' },
    { name: '主管', open_id: 'ou_head', department: 'QC' },
  ],
  fetchOosOotReportRecords: async () => ({ data: [{ record_id: 'rec_report', content: '报告内容', report_department: 'QC', reporter: '原人员', attachments: [{ name: '报告.doc', file_token: 'ft_doc' }, { name: '外部链接', url: 'https://example.test/report' }] }] }),
  fetchOosOotInvestigationPushRecords: async () => ({ data: [{ record_id: 'rec_push', oos_oot_code: 'OOS-1', push_round: '第1次', department: 'QC', submitter: '原人员', department_head_direct: '主管', investigation_report_url: 'https://example.test/investigation' }] }),
  fetchOosLedgerRecords: async () => ({ data: [{ investigation_code: 'OOS-1' }] }),
  fetchOotLedgerRecords: async () => ({ data: [] }),
  fetchCapaPlanTracks: async () => ({ items: [{ id: 'plan', capa_id: 'capa', capa_code: 'CA-1', plan_content: '计划内容', owner_name: '原人员', department: 'QC', department_head: '主管', owner_confirmed: false, department_head_confirmed: false, reminder_status: 'pending' }] }),
  fetchCapa: async () => ({ id: 'capa', title: '措施', capa_code: 'CA-1', status: 'draft' }),
  fetchCapas: async () => ({ items: [{ id: 'capa', capa_code: 'CA-1', title: '措施' }] }),
  fetchProductDepartmentRecords: async () => ({ data: [{ record_id: 'rec_product', product_code: 'MV', fermentation_department: 'QC', fermentation_head: '原人员', extraction_department: 'QC', extraction_head: '主管' }] }),
}))
vi.mock('./FeishuAttachmentPreviewModal', () => ({ FeishuAttachmentPreviewModal: ({ previewSrc, downloadSrc }: { previewSrc: string; downloadSrc: string }) => <div role="document" data-preview={previewSrc} data-download={downloadSrc} /> }))
vi.mock('./CapaImportDrawer', () => ({ CapaImportDrawer: () => null }))

import { feishuColumnLayouts } from './feishuColumnLayout'
import OosOotReportRecordPage from './OosOotReportRecordPage'
import OosOotInvestigationPushPage from './OosOotInvestigationPushPage'
import { CapaDetail } from './CapaDetail'
import { CapaTable } from './CapaTable'
import { CapaPlanTrackPage } from './CapaPlanTrackPage'
import { OosOotLedgerPageBase, type OosOotLedgerRecord } from './OosOotLedgerPageBase'
import OosOotProductDepartmentPage from './OosOotProductDepartmentPage'

let root: Root
let container: HTMLDivElement
let client: QueryClient
beforeEach(() => {
  vi.clearAllMocks()
  mocks.report.mockResolvedValue({})
  mocks.investigation.mockResolvedValue({})
  mocks.capa.mockResolvedValue({})
  mocks.product.mockResolvedValue({})
  container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
})
afterEach(async () => {
  await act(async () => root.unmount())
  client.clear()
  container.remove()
  vi.restoreAllMocks()
})
async function renderPage(page: React.ReactNode) {
  await act(async () => root.render(<ConfigProvider locale={zhCN}><App><QueryClientProvider client={client}>{page}</QueryClientProvider></App></ConfigProvider>))
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 50)) })
}
async function button(text: string) {
  const element = Array.from(document.querySelectorAll('button')).find(button => button.textContent?.replace(/\s/g, '') === text)
  expect(element).toBeTruthy()
  await act(async () => element!.click())
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 20)) })
}
async function choose(field: string, text: string) {
  const input = document.querySelector(`#${field}`)!
  expect(input).toBeTruthy()
  await act(async () => input.dispatchEvent(new MouseEvent('mousedown', { bubbles: true })))
  const option = Array.from(document.querySelectorAll('.ant-select-item-option')).find(el => el.textContent?.includes(text))
  expect(option).toBeTruthy()
  await act(async () => option!.dispatchEvent(new MouseEvent('click', { bubbles: true })))
}

it('OOS report changes reporter without sending attachment fields', async () => {
  await renderPage(<OosOotReportRecordPage />)
  const headers = Array.from(container.querySelectorAll('th')).map(el => el.textContent)
  expect(headers).toEqual([...feishuColumnLayouts.oosReport, '操作'])
  await button('修改')
  await choose('reporter', '新人员')
  await button('确定')
  expect(mocks.report).toHaveBeenCalledWith('rec_report', expect.objectContaining({ reporter: 'ou_new' }))
  expect(mocks.report.mock.calls[0][1]).not.toHaveProperty('attachments')
})

it('CAPA ledger renders every Feishu column in order and keeps local-only columns out of the list', async () => {
  await renderPage(<CapaTable capas={[]} total={0} />)
  expect(Array.from(container.querySelectorAll('th')).map(node => node.textContent).filter(Boolean)).toEqual([
    ...feishuColumnLayouts.capaLedger, '操作',
  ])
})

it('OOS report keeps existing reporter if only text was edited', async () => {
  await renderPage(<OosOotReportRecordPage />)
  await button('修改')
  await button('确定')
  expect(mocks.report).toHaveBeenCalled()
  expect(mocks.report.mock.calls[0][1]).not.toHaveProperty('reporter')
})

it('OOS uploaded documents use protected preview and real links open directly', async () => {
  await renderPage(<OosOotReportRecordPage />)
  const open = vi.spyOn(window, 'open').mockReturnValue(null)
  await button('外部链接')
  expect(open).toHaveBeenCalledWith('https://example.test/report', '_blank', 'noopener,noreferrer')
  await button('报告.doc')
  const preview = document.querySelector('[role="document"]')!
  expect(preview.getAttribute('data-preview')).toBe('/api/v1/quality/oos-oot/report-records/rec_report/attachments/ft_doc/preview')
  expect(preview.getAttribute('data-download')).toBe('/api/v1/quality/oos-oot/report-records/rec_report/attachments/ft_doc/content')
})

it('OOS investigation saves selected submitter without clearing head or report URL', async () => {
  await renderPage(<OosOotInvestigationPushPage />)
  expect(Array.from(container.querySelectorAll('th')).map(el => el.textContent)).toEqual([...feishuColumnLayouts.oosInvestigation, '操作'])
  expect(container.querySelector('a[href="https://example.test/investigation"]')?.getAttribute('target')).toBe('_blank')
  await button('修改')
  await choose('submitter', '新人员')
  await button('确定')
  expect(mocks.investigation).toHaveBeenCalledWith('rec_push', expect.objectContaining({ submitter: 'ou_new' }))
  expect(mocks.investigation.mock.calls[0][1]).not.toHaveProperty('department_head_direct')
  expect(mocks.investigation.mock.calls[0][1]).not.toHaveProperty('investigation_report_url')
})

it('OOS investigation keeps validation errors in the form without attempting a save', async () => {
  await renderPage(<OosOotInvestigationPushPage />)
  await button('修改')
  const clear = document.querySelector('#oos_oot_code')!.closest('.ant-select')!.querySelector('.ant-select-clear')!
  expect(clear).toBeTruthy()
  await act(async () => clear.dispatchEvent(new MouseEvent('mousedown', { bubbles: true })))
  await button('确定')
  expect(mocks.investigation).not.toHaveBeenCalled()
  expect(document.querySelector('.ant-form-item-explain-error')?.textContent).toBe('请选择OOS/OOT编号')
  expect(document.querySelector('.ant-modal-title')?.textContent).toBe('修改调查推送记录')
})

it('CAPA owner switch preserves department head and existing confirmation values', async () => {
  await renderPage(<CapaPlanTrackPage />)
  const headers = Array.from(container.querySelectorAll('th')).map(el => el.textContent)
  expect(headers).toEqual([...feishuColumnLayouts.capaPlan, '操作'])
  await button('编辑')
  expect(document.querySelector<HTMLInputElement>('input[aria-label="部门负责人"]')?.readOnly).toBe(true)
  expect(Array.from(document.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')).every(input => input.disabled)).toBe(true)
  await choose('owner_name', '新人员')
  await button('确定')
  expect(mocks.capa).toHaveBeenCalledWith('plan', expect.objectContaining({ owner_name: '新人员', department: 'QC' }))
  expect(mocks.capa.mock.calls[0][1]).not.toHaveProperty('department_head')
  expect(mocks.capa.mock.calls[0][1]).not.toHaveProperty('owner_confirmed')
  expect(mocks.capa.mock.calls[0][1]).not.toHaveProperty('department_head_confirmed')
})

it('CAPA plan details keep the linked CAPA navigation', async () => {
  await renderPage(<CapaPlanTrackPage />)
  await button('详情')
  const drawer = document.querySelector('.ant-drawer')!
  expect(drawer.textContent).toContain('CAPA计划跟踪详情')
  expect(drawer.textContent).toContain('计划内容')
  expect(drawer.textContent).toContain('主管')
  expect(drawer.querySelector('a[href="/quality/capas/capa"]')?.textContent).toBe('CA-1')
})

it.each(['OOS', 'OOT'] as const)('%s ledger saves a selected registrant ID and retains edited information', async (label) => {
  const update = vi.fn().mockResolvedValue({})
  const record: OosOotLedgerRecord = {
    record_id: 'rec_ledger', serial_number: '1', date: '2026-09-22', material_name: '物料',
    batch_number: 'B-1', investigation_code: 'INV-1', problem_description: '问题', root_cause: '原因',
    corrective_actions: '措施', final_disposition: '处理', registrant: '原人员', remark: '备注',
  }
  await renderPage(<OosOotLedgerPageBase config={{
    label, queryKeyPrefix: 'ledger', exportUrl: '/export', fetchRecords: async () => ({ data: [record] }),
    pullRecords: vi.fn(), createRecord: vi.fn(), updateRecord: update, deleteRecord: vi.fn(),
  }} />)
  expect(Array.from(container.querySelectorAll('th')).map(el => el.textContent)).toEqual([...feishuColumnLayouts.oosLedger, '操作'])
  await button('修改')
  await choose('registrant', '新人员')
  await button('保存')
  expect(update).toHaveBeenCalledWith('rec_ledger', expect.objectContaining({ registrant: 'ou_new', problem_description: '问题', remark: '备注' }))
})

it('product departments change one person without rewriting the other existing person', async () => {
  await renderPage(<OosOotProductDepartmentPage />)
  expect(Array.from(container.querySelectorAll('th')).map(el => el.textContent)).toEqual([...feishuColumnLayouts.productDepartment, '操作'])
  await button('修改')
  await choose('fermentation_head', '新人员')
  await button('确定')
  expect(mocks.product).toHaveBeenCalledWith('rec_product', expect.objectContaining({ fermentation_head: 'ou_new', product_code: 'MV' }))
  expect(mocks.product.mock.calls[0][1]).not.toHaveProperty('extraction_head')
})

it('CAPA save reports Feishu sync failure instead of reporting full success', async () => {
  mocks.capa.mockResolvedValue({ feishu_sync_status: 'failed' })
  await renderPage(<CapaPlanTrackPage />)
  await button('编辑')
  await button('确定')
  expect(document.body.textContent).toContain('计划已保存，但飞书同步失败')
  expect(document.body.textContent).not.toContain('CAPA计划跟踪已更新')
})


it('CAPA detail shows a warning when the saved update did not sync to Feishu', async () => {
  mocks.saveDetail.mockResolvedValue({ success: true, feishu_sync_status: 'failed' })
  await renderPage(<CapaDetail />)
  await button('编辑')
  await button('保存')
  expect(mocks.saveDetail).toHaveBeenCalled()
  expect(document.body.textContent).toContain('CAPA已保存，但飞书同步失败')
})

it('CAPA plan creation includes department but never writes automation confirmations', async () => {
  mocks.createPlan.mockResolvedValue({ feishu_sync_status: 'failed' })
  await renderPage(<CapaPlanTrackPage />)
  await button('新增计划跟踪')
  await choose('capa_id', 'CA-1')
  const input = document.querySelector<HTMLTextAreaElement>('#plan_content')!
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')!.set!.call(input, '新计划')
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await choose('department', 'QC')
  await button('确定')
  expect(mocks.createPlan).toHaveBeenCalledWith(expect.objectContaining({ department: 'QC', plan_content: '新计划' }))
  expect(mocks.createPlan.mock.calls[0][0]).not.toHaveProperty('department_head')
  expect(mocks.createPlan.mock.calls[0][0]).not.toHaveProperty('owner_confirmed')
  expect(mocks.createPlan.mock.calls[0][0]).not.toHaveProperty('department_head_confirmed')
  expect(document.body.textContent).toContain('计划已创建，但飞书同步失败')
})
