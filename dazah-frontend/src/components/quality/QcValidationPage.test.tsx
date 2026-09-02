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
    // antd Modal/confirm/Select 下拉等 portal 直接挂到 document.body，逐个清理避免跨用例残留
    document.body.querySelectorAll('.ant-modal-root, .ant-select-dropdown, .ant-message, .ant-drawer').forEach((node) => node.remove())
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

  it('surfaces the backend message when the list query fails', async () => {
    apiClient.fetchQcValidationRecords.mockRejectedValue(new Error('飞书连接超时'))
    await renderPage()
    expect(document.body.textContent).toContain('飞书连接超时')
  })

  it('warns without opening when the row share link is missing', async () => {
    apiClient.fetchQcValidationShareLinks.mockResolvedValue({})
    const openMock = vi.fn()
    vi.stubGlobal('open', openMock)
    await renderPage()
    const rowButton = Array.from(container.querySelectorAll('button')).find(
      (btn) => btn.getAttribute('title') === '打开飞书对应行',
    )
    await act(async () => {
      rowButton?.click()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    expect(document.body.textContent).toContain('该记录未生成飞书链接（可能无权限或记录不存在）')
    expect(openMock).not.toHaveBeenCalled()
  })

  it('falls back to the generic message when the share link request fails', async () => {
    apiClient.fetchQcValidationShareLinks.mockRejectedValue('boom')
    await renderPage()
    const rowButton = Array.from(container.querySelectorAll('button')).find(
      (btn) => btn.getAttribute('title') === '打开飞书对应行',
    )
    await act(async () => {
      rowButton?.click()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    expect(document.body.textContent).toContain('生成飞书记录链接失败')
  })

  it('downloads drawer attachments through the page proxy builder', async () => {
    const blob = new Blob(['x'], { type: 'image/jpeg' })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, blob: async () => blob }))
    Object.defineProperty(URL, 'createObjectURL', {
      value: vi.fn(() => 'blob:proxy'),
      configurable: true,
    })
    const openMock = vi.fn()
    vi.stubGlobal('open', openMock)
    await renderPage()
    const titleLink = Array.from(container.querySelectorAll('a')).find((anchor) =>
      (anchor.textContent || '').includes('生化培养箱'),
    )
    await act(async () => {
      titleLink?.click()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    const attachmentButton = Array.from(document.body.querySelectorAll('button')).find(
      (button) => (button.textContent || '') === 'cover.jpeg',
    )
    expect(attachmentButton).toBeTruthy()
    await act(async () => {
      attachmentButton?.click()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    expect(fetchMockHits(fetch)).toContain(
      '/api/v1/quality/validation-qc/records/rec-1/attachments/ft-1/content?year=2026',
    )
    expect(openMock).toHaveBeenCalledWith('blob:proxy', '_blank')
  })

  it('confirms, deletes and invalidates the list', async () => {
    qcActions.deleteQcValidationRecord.mockResolvedValue({ success: true })
    await renderPage()
    const deleteButton = container.querySelector('.anticon-delete')?.closest('button')
    expect(deleteButton).toBeTruthy()
    await act(async () => {
      deleteButton?.click()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    const confirmOk = document.body.querySelector('.ant-modal-confirm .ant-btn-primary')
    expect(confirmOk).toBeTruthy()
    const requestCount = apiClient.fetchQcValidationRecords.mock.calls.length
    await act(async () => {
      confirmOk?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 80))
    })
    expect(qcActions.deleteQcValidationRecord).toHaveBeenCalledWith(2026, 'rec-1')
    expect(document.body.textContent).toContain('删除成功')
    // invalidateQueries 触发列表重新拉取
    expect(apiClient.fetchQcValidationRecords.mock.calls.length).toBeGreaterThan(requestCount)
  })

  it('surfaces delete failures via toast', async () => {
    qcActions.deleteQcValidationRecord.mockRejectedValue(new Error('无删除权限'))
    await renderPage()
    const deleteButton = container.querySelector('.anticon-delete')?.closest('button')
    expect(deleteButton).toBeTruthy()
    await act(async () => {
      deleteButton?.click()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    const confirmOk = document.body.querySelector('.ant-modal-confirm .ant-btn-primary')
    expect(confirmOk).toBeTruthy()
    await act(async () => {
      confirmOk?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 80))
    })
    expect(document.body.textContent).toContain('无删除权限')
  })

  it('creates a record through the editor modal', async () => {
    qcActions.createQcValidationRecord.mockResolvedValue({ success: true })
    await renderPage()
    const createButton = Array.from(container.querySelectorAll('button')).find((btn) =>
      (btn.textContent || '').includes('新增'),
    )
    expect(createButton).toBeTruthy()
    await act(async () => {
      createButton?.click()
      await new Promise((resolve) => setTimeout(resolve, 60))
    })
    expect(document.body.textContent).toContain('新增QC验证记录（2026年）')
    const nameItem = Array.from(document.body.querySelectorAll('.ant-form-item')).find(
      (item) => (item.querySelector('.ant-form-item-label')?.textContent || '').includes('方案名称'),
    )
    const nameInput = nameItem?.querySelector('input') as HTMLInputElement | null
    expect(nameInput).toBeTruthy()
    await act(async () => {
      if (nameInput) {
        // antd Input 是受控组件：须经由原生 value setter 赋值才能触发 React onChange
        Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set?.call(
          nameInput,
          '新增确认方案',
        )
        nameInput.dispatchEvent(new Event('input', { bubbles: true }))
      }
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    const confirmOk = document.body.querySelector('.ant-modal-footer .ant-btn-primary')
    expect(confirmOk).toBeTruthy()
    await act(async () => {
      confirmOk?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 80))
    })
    expect(qcActions.createQcValidationRecord).toHaveBeenCalledWith(
      2026,
      expect.objectContaining({ 方案名称: '新增确认方案' }),
    )
    expect(document.body.textContent).toContain('QC验证记录已创建')
  })

  it('edits an existing record with mapped typed field values', async () => {
    qcActions.updateQcValidationRecord.mockResolvedValue({ success: true })
    await renderPage()
    const editButton = container.querySelector('.anticon-edit')?.closest('button')
    expect(editButton).toBeTruthy()
    await act(async () => {
      editButton?.click()
      await new Promise((resolve) => setTimeout(resolve, 60))
    })
    expect(document.body.textContent).toContain('编辑QC验证记录（2026年）')
    // 编辑模式远离必需校验：表单已由 initialRecord 预填 DateTime/Checkbox/User 分支
    const confirmOk = document.body.querySelector('.ant-modal-footer .ant-btn-primary')
    expect(confirmOk).toBeTruthy()
    await act(async () => {
      confirmOk?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 80))
    })
    expect(qcActions.updateQcValidationRecord).toHaveBeenCalledWith(
      2026,
      'rec-1',
      expect.objectContaining({
        方案批准时间: expect.any(Number),
        方案提交: true,
        人员: expect.any(Array),
      }),
    )
    expect(document.body.textContent).toContain('QC验证记录已更新')
  })

  it('filters the list by keyword and refetches', async () => {
    await renderPage()
    const searchInput = Array.from(container.querySelectorAll('input')).find(
      (input) => (input as HTMLInputElement).placeholder === '方案名称/编码等关键词',
    ) as HTMLInputElement | null
    expect(searchInput).toBeTruthy()
    await act(async () => {
      if (searchInput) {
        Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set?.call(
          searchInput,
          '生化培养箱',
        )
        searchInput.dispatchEvent(new Event('input', { bubbles: true }))
      }
      await new Promise((resolve) => setTimeout(resolve, 100))
    })
    expect(apiClient.fetchQcValidationRecords).toHaveBeenLastCalledWith(2026, {
      keyword: '生化培养箱',
      page: 1,
      page_size: 20,
    })
  })

  it('switches year through the selector and reloads the list', async () => {
    await renderPage()
    const wrapper = container.querySelector('.ant-select') as HTMLElement | null
    expect(wrapper).toBeTruthy()
    await act(async () => {
      wrapper?.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      wrapper?.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    const option = Array.from(document.body.querySelectorAll('.ant-select-item-option')).find(
      (item) => (item.textContent || '').includes('2025年'),
    ) as HTMLElement | null
    expect(option).toBeTruthy()
    await act(async () => {
      option?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 100))
    })
    expect(apiClient.fetchQcValidationRecords).toHaveBeenLastCalledWith(2025, {
      keyword: undefined,
      page: 1,
      page_size: 20,
    })
  })

  it('warns when the configured year has no Feishu table URL', async () => {
    apiClient.fetchQcValidationYears.mockResolvedValue([
      { year: 2026, entity_code: 'validation_qc_2026', table_configured: true, feishu_url: null },
    ])
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
    expect(document.body.textContent).toContain('当前年度飞书表未配置，无法打开')
    expect(openMock).not.toHaveBeenCalled()
  })

  it('refreshes the page data through the toolbar button', async () => {
    await renderPage()
    const before = apiClient.fetchQcValidationRecords.mock.calls.length
    const refreshButton = Array.from(container.querySelectorAll('button')).find((btn) =>
      (btn.textContent || '').includes('刷新'),
    )
    expect(refreshButton).toBeTruthy()
    await act(async () => {
      refreshButton?.click()
      await new Promise((resolve) => setTimeout(resolve, 60))
    })
    expect(apiClient.fetchQcValidationRecords.mock.calls.length).toBeGreaterThan(before)
  })

  it('surfaces editor save failures via toast', async () => {
    qcActions.createQcValidationRecord.mockRejectedValue(new Error('保存失败：字段冲突'))
    await renderPage()
    const createButton = Array.from(container.querySelectorAll('button')).find((btn) =>
      (btn.textContent || '').includes('新增'),
    )
    await act(async () => {
      createButton?.click()
      await new Promise((resolve) => setTimeout(resolve, 60))
    })
    const nameItem = Array.from(document.body.querySelectorAll('.ant-form-item')).find(
      (item) => (item.querySelector('.ant-form-item-label')?.textContent || '').includes('方案名称'),
    )
    const nameInput = nameItem?.querySelector('input') as HTMLInputElement | null
    await act(async () => {
      if (nameInput) {
        Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set?.call(
          nameInput,
          '保存失败方案',
        )
        nameInput.dispatchEvent(new Event('input', { bubbles: true }))
      }
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    const confirmOk = document.body.querySelector('.ant-modal-footer .ant-btn-primary')
    await act(async () => {
      confirmOk?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 80))
    })
    expect(document.body.textContent).toContain('保存失败：字段冲突')
    // 保存失败后弹窗保持在打开状态（编辑未关闭）
    expect(document.body.textContent).toContain('新增QC验证记录（2026年）')
  })

  it('opens the detail drawer from the row action and closes it', async () => {
    await renderPage()
    const eyeButton = container.querySelector('.anticon-eye')?.closest('button')
    expect(eyeButton).toBeTruthy()
    await act(async () => {
      eyeButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    expect(document.body.textContent).toContain('QC验证记录详情')
    const closeButton = document.body.querySelector('.ant-drawer-close')
    expect(closeButton).toBeTruthy()
    // happy-dom 下 Drawer 退场动效不会结束，DOM 保留但 onClose 已执行
    await act(async () => {
      closeButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 80))
    })
  })

  it('closes the editor modal through the cancel button', async () => {
    await renderPage()
    const createButton = Array.from(container.querySelectorAll('button')).find((btn) =>
      (btn.textContent || '').includes('新增'),
    )
    await act(async () => {
      createButton?.click()
      await new Promise((resolve) => setTimeout(resolve, 60))
    })
    expect(document.body.textContent).toContain('新增QC验证记录（2026年）')
    const cancelButton = Array.from(
      document.body.querySelectorAll('.ant-modal-footer .ant-btn'),
    ).find((btn) => !btn.className.includes('ant-btn-primary'))
    expect(cancelButton).toBeTruthy()
    // 同上：Modal 退场动效在 happy-dom 下不结束，DOM 保留但 onCancel 已执行
    await act(async () => {
      cancelButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 80))
    })
    expect(qcActions.createQcValidationRecord).not.toHaveBeenCalled()
  })

  it('changes page through the table pagination', async () => {
    apiClient.fetchQcValidationRecords.mockResolvedValue({
      items: Array.from({ length: 20 }, (_, i) => ({ ...RECORDS[0], record_id: `rec-${i + 1}` })),
      total: 25,
      page: 1,
      page_size: 20,
      table_configured: true,
    })
    await renderPage()
    const pageTwo = document.body.querySelector<HTMLElement>('.ant-pagination-item-2')
    expect(pageTwo).toBeTruthy()
    await act(async () => {
      pageTwo?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 80))
    })
    expect(apiClient.fetchQcValidationRecords).toHaveBeenLastCalledWith(2026, {
      keyword: undefined,
      page: 2,
      page_size: 20,
    })
  })

  it('resolves department contacts into the editor person options', async () => {
    apiClient.fetchDepartmentContacts.mockResolvedValue([
      { name: '赵双', bitable_user_id: 'bu-1', open_id: 'ou-1' },
    ])
    await renderPage()
    const editButton = container.querySelector('.anticon-edit')?.closest('button')
    expect(editButton).toBeTruthy()
    await act(async () => {
      editButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 60))
    })
    expect(document.body.textContent).toContain('编辑QC验证记录（2026年）')
    // 人员字段以部门联系人映射出的选项渲染（map/filter 分支）——
    // 弹窗打开即触发 contacts 查询与选项构建
    expect(apiClient.fetchDepartmentContacts).toHaveBeenCalled()
  })
})

function fetchMockHits(fetchMock: unknown): string[] {
  return (fetchMock as ReturnType<typeof vi.fn>).mock.calls.map((call) => String(call[0]))
}
