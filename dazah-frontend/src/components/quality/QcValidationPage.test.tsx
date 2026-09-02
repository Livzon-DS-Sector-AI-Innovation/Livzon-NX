/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiClient = vi.hoisted(() => ({
  fetchQcValidationYears: vi.fn(),
  fetchQcValidationFields: vi.fn(),
  fetchQcValidationRecords: vi.fn(),
  fetchQcValidationShareLinks: vi.fn(),
  fetchDepartmentContacts: vi.fn(),
}))

const qcActions = vi.hoisted(() => ({
  createQcValidationRecord: vi.fn(),
  updateQcValidationRecord: vi.fn(),
  deleteQcValidationRecord: vi.fn(),
}))

vi.mock('@/lib/api/client/quality', () => apiClient)
vi.mock('@/actions/quality-validation-qc', () => qcActions)

import { QcValidationPage } from './QcValidationPage'

const FIELD_METAS = [
  { field_name: '方案名称', ui_type: 'Text', editable: true, options: null },
  { field_name: '方案编码', ui_type: 'Text', editable: true, options: null },
  { field_name: '方案批准时间', ui_type: 'DateTime', editable: true, options: null },
  { field_name: '报告批准时间', ui_type: 'DateTime', editable: true, options: null },
  { field_name: '验证原因', ui_type: 'SingleSelect', editable: true, options: [{ name: '周期性' }] },
  { field_name: '偏差情况', ui_type: 'SingleSelect', editable: true, options: [{ name: '无' }] },
  { field_name: '验证结果', ui_type: 'SingleSelect', editable: true, options: [{ name: '通过' }] },
  { field_name: '再验证周期（年）', ui_type: 'Text', editable: true, options: null },
  { field_name: '产品', ui_type: 'SingleSelect', editable: true, options: [{ name: '公用' }] },
  { field_name: '人员', ui_type: 'User', editable: true, options: null },
  { field_name: '状态', ui_type: 'SingleSelect', editable: true, options: [{ name: '已完成' }] },
  { field_name: '方案提交', ui_type: 'Checkbox', editable: true, options: null },
  { field_name: '报告提交', ui_type: 'Checkbox', editable: true, options: null },
  { field_name: '封面照片', ui_type: 'Attachment', editable: false, options: null },
  { field_name: '设备/房间编码', ui_type: 'Text', editable: true, options: null },
  { field_name: '备注', ui_type: 'Text', editable: true, options: null },
  { field_name: '同步', ui_type: 'Button', editable: false, options: null },
]

const RECORDS = [
  {
    record_id: 'rec-1',
    方案名称: '生化培养箱(QC-2-2-066)再确认方案',
    方案编码: 'VP-QC-IQ/OQ/PQ2601-01',
    方案批准时间: new Date(2026, 0, 30).getTime(),
    报告批准时间: new Date(2026, 2, 26).getTime(),
    验证原因: '周期性',
    偏差情况: '无',
    验证结果: '通过',
    '再验证周期（年）': '3',
    产品: '公用',
    人员: [{ id: 'ou_1', name: '赵双', avatar_url: '' }],
    状态: '已完成',
    方案提交: 'True',
    报告提交: 'True',
    封面照片: [{ name: 'cover.jpeg', file_token: 'ft-1', url: '', size: 10 }],
    '设备/房间编码': 'QC-2-2-066',
    备注: '/',
  },
]

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
}

describe('QcValidationPage', () => {
  let root: Root
  let container: HTMLElement

  beforeEach(() => {
    apiClient.fetchQcValidationYears.mockResolvedValue([
      { year: 2025, entity_code: 'validation_qc_2025', table_configured: false, feishu_url: null },
      { year: 2026, entity_code: 'validation_qc_2026', table_configured: true, feishu_url: 'https://www.feishu.cn/base/tok_2026?table=tbl_2026' },
    ])
    apiClient.fetchQcValidationFields.mockResolvedValue({ fields: FIELD_METAS, can_push: true })
    apiClient.fetchQcValidationRecords.mockResolvedValue({
      items: RECORDS,
      total: 1,
      page: 1,
      page_size: 20,
      table_configured: true,
    })
    apiClient.fetchDepartmentContacts.mockResolvedValue([])
    apiClient.fetchQcValidationShareLinks.mockResolvedValue({
      'rec-1': 'https://j0eukrlohu.feishu.cn/record/tok-rec-1',
    })
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    vi.clearAllMocks()
  })

  async function renderPage() {
    act(() => {
      root.render(
        <QueryClientProvider client={makeQueryClient()}>
          <App>
            <QcValidationPage />
          </App>
        </QueryClientProvider>,
      )
    })
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 60))
    })
  }

  it('renders list columns from 方案名称 to 人员 with records', async () => {
    await renderPage()
    const text = container.textContent || ''
    expect(text).toContain('QC验证（2026年）')
    expect(text).toContain('生化培养箱(QC-2-2-066)再确认方案')
    expect(text).toContain('VP-QC-IQ/OQ/PQ2601-01')
    expect(text).toContain('赵双')
    expect(apiClient.fetchQcValidationRecords).toHaveBeenCalledWith(2026, {
      keyword: undefined,
      page: 1,
      page_size: 20,
    })
  })

  it('opens detail drawer with full fields incl. attachments when clicking title', async () => {
    await renderPage()
    const titleLink = Array.from(container.querySelectorAll('a')).find((anchor) =>
      (anchor.textContent || '').includes('生化培养箱'),
    )
    expect(titleLink).toBeTruthy()
    await act(async () => {
      titleLink?.click()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    // antd Drawer 渲染到 body 门户
    const text = document.body.textContent || ''
    expect(text).toContain('QC验证记录详情')
    expect(text).toContain('设备/房间编码')
    expect(text).toContain('QC-2-2-066')
    expect(text).toContain('备注')
    expect(text).toContain('封面照片')
    expect(text).toContain('是')
    const attachmentButton = Array.from(document.body.querySelectorAll('button')).find(
      (button) => (button.textContent || '') === 'cover.jpeg',
    )
    expect(attachmentButton).toBeTruthy()
  })

  it('warns when the year table is not configured', async () => {
    apiClient.fetchQcValidationYears.mockResolvedValue([
      { year: 2026, entity_code: 'validation_qc_2026', table_configured: false, feishu_url: null },
    ])
    apiClient.fetchQcValidationRecords.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
      table_configured: false,
    })
    await renderPage()
    const text = container.textContent || ''
    expect(text).toContain('2026 年 QC验证飞书表未配置')
  })

  it('opens the Feishu table link from the toolbar button', async () => {
    const openMock = vi.fn()
    vi.stubGlobal('open', openMock)
    await renderPage()
    const button = Array.from(container.querySelectorAll('button')).find(
      (btn) => (btn.textContent || '').includes('打开飞书表格'),
    )
    expect(button).toBeTruthy()
    await act(async () => {
      button?.click()
    })
    expect(openMock).toHaveBeenCalledWith(
      'https://www.feishu.cn/base/tok_2026?table=tbl_2026',
      '_blank',
      'noopener,noreferrer',
    )
  })

  it('opens the per-row Feishu share link from the row action', async () => {
    const openMock = vi.fn()
    vi.stubGlobal('open', openMock)
    await renderPage()
    // 操作列第一行第一个图标按钮（打开飞书对应行）——通过 title 定位
    const rowButton = Array.from(container.querySelectorAll('button')).find(
      (btn) => btn.getAttribute('title') === '打开飞书对应行',
    )
    expect(rowButton).toBeTruthy()
    await act(async () => {
      rowButton?.click()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    expect(apiClient.fetchQcValidationShareLinks).toHaveBeenCalledWith(2026, ['rec-1'])
    expect(openMock).toHaveBeenCalledWith(
      'https://j0eukrlohu.feishu.cn/record/tok-rec-1',
      '_blank',
      'noopener,noreferrer',
    )
  })
})
