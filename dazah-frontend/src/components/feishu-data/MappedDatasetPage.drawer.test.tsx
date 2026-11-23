/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const navigation = vi.hoisted(() => ({ replace: vi.fn() }))
const mappedApi = vi.hoisted(() => ({
  fetchMappedPageData: vi.fn(),
  fetchMappedPageDataset: vi.fn(),
  mappedAttachmentUrl: vi.fn(() => '/attachment'),
  fetchPersonAvatars: vi.fn(async () => ({})),
}))

vi.mock('next/navigation', () => ({
  useRouter: () => navigation,
  useSearchParams: () => new URLSearchParams('dataset=binding-1'),
}))
vi.mock('@/lib/api/mapped-feishu', () => mappedApi)

import { MappedDatasetPage } from './MappedDatasetPage'

let root: Root
let container: HTMLElement

const pageData = {
  bindings: [{ id: 'binding-1', tab_label: '记录', is_default: true, table: { app_token: 'app-1' } }],
}

beforeEach(() => {
  container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
  mappedApi.fetchMappedPageDataset.mockResolvedValue({
    fields: [
      { field_id: 'applicant', field_name: '申请人' },
      { field_id: 'stamp_date', field_name: '用印日期' },
      { field_id: 'attachment', field_name: '上传用印文件' },
    ],
    records: [
      {
        record_id: 'record-1',
        fields: {
          申请人: [{ id: 'ou_abc', name: '常晶晶', email: 'chang@livzon.cn' }],
          用印日期: 1782230400000,
          上传用印文件: [{ name: 'photo_1782284929497.JPEG', file_token: 'file-1', type: 'image/jpeg' }],
        },
      },
    ],
    pagination: { page: 1, page_size: 50, total: 1 },
  })
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
  vi.clearAllMocks()
})

function renderPage() {
  act(() => root.render(<MappedDatasetPage
    pageKey="warehouse.records"
    title="仓储记录"
    initialPageData={pageData}
  />))
}

it('opens full record details from a row click with attachment preview', async () => {
  renderPage()
  await act(async () => { await mappedApi.fetchMappedPageDataset.mock.results[0]?.value })

  // 单元格不再提供字段级按钮，整行可点击
  const detailButton = [...container.querySelectorAll('button')].find((button) => button.textContent?.includes('photo_1782284929497'))
  expect(detailButton).toBeUndefined()

  const row = container.querySelector('.ant-table-row')
  expect(row).toBeTruthy()
  act(() => row?.dispatchEvent(new MouseEvent('click', { bubbles: true })))

  const drawer = document.body.querySelector('.ant-drawer-content-wrapper')
  expect(drawer?.getAttribute('style')).toContain('width: 720px')
  // 字段详情含人员姓名与附件预览/下载
  expect(drawer?.textContent).toContain('常晶晶')
  const previewImage = document.body.querySelector('.ant-drawer-content-wrapper img')
  expect(previewImage?.getAttribute('src')).toBe('/attachment')
  const downloadLink = [...document.body.querySelectorAll('.ant-drawer-content-wrapper a')]
    .find((link) => link.textContent?.includes('photo_1782284929497.JPEG'))
  expect(downloadLink?.getAttribute('href')).toBe('/attachment')
})

it('renders millisecond timestamps as date-only and persons without raw ids', async () => {
  renderPage()
  await act(async () => { await mappedApi.fetchMappedPageDataset.mock.results[0]?.value })

  const text = container.textContent || ''
  expect(text).not.toContain('1782230400000')
  expect(text).not.toContain('ou_abc')
  expect(text).toContain('常晶晶')
  // 零点时间戳只显示日期，不带 00:00:00
  const expectedDate = new Date(1782230400000).toLocaleDateString('zh-CN', {
    timeZone: 'Asia/Shanghai',
  })
  expect(text).toContain(expectedDate)
  expect(text).not.toContain('00:00:00')
})

it('never renders a serial-number column even if the base has one', async () => {
  mappedApi.fetchMappedPageDataset.mockResolvedValue({
    fields: [
      { field_id: 'serial', field_name: '序号' },
      { field_id: 'applicant', field_name: '申请人' },
    ],
    records: [
      {
        record_id: 'record-1',
        fields: { 序号: '7', 申请人: [{ id: 'ou_abc', name: '常晶晶', email: 'chang@livzon.cn' }] },
      },
    ],
    pagination: { page: 1, page_size: 50, total: 1 },
  })
  renderPage()
  await act(async () => { await mappedApi.fetchMappedPageDataset.mock.results[0]?.value })
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 50)) })

  const headerCells = [...container.querySelectorAll('.ant-table-thead th')].map((cell) => cell.textContent)
  expect(headerCells).not.toContain('序号')
})

it('resolves person avatars when enabled', async () => {
  mappedApi.fetchPersonAvatars.mockResolvedValue({ 'chang@livzon.cn': 'https://avatar.example/c.png' })
  act(() => root.render(<MappedDatasetPage
    pageKey="warehouse.records"
    title="仓储记录"
    initialPageData={pageData}
    enablePersonAvatars
  />))
  await act(async () => {
    await vi.waitFor(() => mappedApi.fetchPersonAvatars.mock.calls.length > 0)
  })

  expect(mappedApi.fetchPersonAvatars).toHaveBeenCalledWith('warehouse', ['chang@livzon.cn'])
  await act(async () => {
    await vi.waitFor(() => container.querySelector('.ant-avatar-image img, img.ant-avatar-image') !== null)
  })
  const avatarImage = container.querySelector('.ant-avatar-image img, img.ant-avatar-image')
  expect(avatarImage?.getAttribute('src')).toBe('https://avatar.example/c.png')
})

it('does not resolve person avatars when not enabled', async () => {
  renderPage()
  await act(async () => { await mappedApi.fetchMappedPageDataset.mock.results[0]?.value })
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 50)) })
  expect(mappedApi.fetchPersonAvatars).not.toHaveBeenCalled()
})

it('puts the date column first, wraps long text, thumbnails in attachment cells', async () => {
  mappedApi.fetchMappedPageDataset.mockResolvedValue({
    fields: [
      { field_id: 'applicant', field_name: '申请人' },
      { field_id: 'stamp_date', field_name: '用印日期', type: 5 },
      { field_id: 'title', field_name: '用印内容（标题）' },
      { field_id: 'empty_note', field_name: '备注' },
      { field_id: 'attachment', field_name: '上传用印文件' },
    ],
    records: [
      {
        record_id: 'record-1',
        fields: {
          申请人: [{ id: 'ou_abc', name: '常晶晶', email: 'chang@livzon.cn' }],
          用印日期: 1782230400000,
          '用印内容（标题）': '关于宁夏隆鼎电力服务协议及后续维护保养事宜的用印申请',
          上传用印文件: [{ name: 'photo.JPEG', file_token: 'file-1', type: 'image/jpeg' }],
          备注: '',
        },
      },
    ],
    pagination: { page: 1, page_size: 50, total: 1 },
  })
  act(() => root.render(<MappedDatasetPage
    pageKey="warehouse.records"
    title="仓储记录"
    initialPageData={pageData}
  />))
  await act(async () => { await mappedApi.fetchMappedPageDataset.mock.results[0]?.value })
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 50)) })

  const headerCells = [...container.querySelectorAll('.ant-table-thead th')].map((cell) => cell.textContent)
  // 日期在首列；整列为空的「备注」与「序号」列都不渲染
  expect(headerCells.slice(0, 2)).toEqual(['用印日期', '申请人'])
  expect(headerCells).not.toContain('备注')
  expect(headerCells).not.toContain('序号')
  // 长文本列不截断：无 ellipsis 类，完整文本直接可见（自动换行）
  const titleHeader = [...container.querySelectorAll('.ant-table-thead th')]
    .find((cell) => cell.textContent === '用印内容（标题）')
  expect(titleHeader?.className).not.toContain('ant-table-cell-ellipsis')
  expect(container.textContent).toContain('关于宁夏隆鼎电力服务协议及后续维护保养事宜的用印申请')
  // 单元格内直接渲染附件缩略图
  const thumb = container.querySelector('.ant-table-row .ant-image img')
  expect(thumb?.getAttribute('src')).toBe('/attachment')
  // 主查询未带排序字段时，自动按日期字段补一次倒序查询
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 50)) })
  const sortCalls = mappedApi.fetchMappedPageDataset.mock.calls
    .filter((call) => call[3]?.sort_field === 'stamp_date')
  expect(sortCalls.length).toBeGreaterThan(0)
  expect(sortCalls[0][3]?.sort_direction).toBe('desc')
})

it('hides fields passed via hiddenFieldNames from the table but keeps them in the drawer', async () => {
  mappedApi.fetchMappedPageDataset.mockResolvedValue({
    fields: [
      { field_id: 'applicant', field_name: '申请人' },
      { field_id: 'approver', field_name: '分管领导' },
      { field_id: 'status', field_name: '审批状态' },
    ],
    records: [
      {
        record_id: 'record-1',
        fields: {
          申请人: [{ id: 'ou_abc', name: '常晶晶', email: 'chang@livzon.cn' }],
          分管领导: [{ id: 'ou_def', name: '吴桐', email: 'wutong@livzon.cn' }],
          审批状态: '审批完成',
        },
      },
    ],
    pagination: { page: 1, page_size: 50, total: 1 },
  })
  act(() => root.render(<MappedDatasetPage
    pageKey="warehouse.records"
    title="仓储记录"
    initialPageData={pageData}
    hiddenFieldNames={['分管领导', '审批状态']}
  />))
  await act(async () => { await mappedApi.fetchMappedPageDataset.mock.results[0]?.value })
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 50)) })

  const headerCells = [...container.querySelectorAll('.ant-table-thead th')].map((cell) => cell.textContent)
  expect(headerCells).not.toContain('分管领导')
  expect(headerCells).not.toContain('审批状态')
  expect(container.textContent).not.toContain('审批完成')

  // 点行后详情抽屉仍完整展示被隐藏的字段
  act(() => container.querySelector('.ant-table-row')?.dispatchEvent(new MouseEvent('click', { bubbles: true })))
  const drawer = document.body.querySelector('.ant-drawer-content-wrapper')
  expect(drawer?.textContent).toContain('审批完成')
  expect(drawer?.textContent).toContain('吴桐')
})

it('renders no description and no sync status strip', async () => {
  renderPage()
  await act(async () => { await mappedApi.fetchMappedPageDataset.mock.results[0]?.value })
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 50)) })

  const text = container.textContent || ''
  expect(text).not.toContain('展示已映射飞书数据表的最后一次完整本地镜像')
  expect(text).not.toContain('数据截至')
  expect(text).not.toContain('未同步')
})

it('shows the tab-matched create button only on its own tab', async () => {
  const pageDataWithTabs = {
    bindings: [
      { id: 'binding-place', tab_label: '放置申请', is_default: true, table: { app_token: 'app-1' } },
      { id: 'binding-req', tab_label: '领用申请', is_default: false, table: { app_token: 'app-1' } },
    ],
  }
  mappedApi.fetchMappedPageDataset.mockResolvedValue({
    fields: [{ field_id: 'dept', field_name: '部门' }],
    records: [{ record_id: 'r1', fields: { 部门: '201-3' } }],
    pagination: { page: 1, page_size: 50, total: 1 },
  })
  act(() => root.render(<MappedDatasetPage
    pageKey="admin:scrap-materials"
    title="废旧物资"
    initialPageData={pageDataWithTabs}
    createForms={[
      { tabLabel: '放置申请', label: '新增放置申请', url: 'https://forms.example/placement' },
      { tabLabel: '领用申请', label: '新增领用申请', url: 'https://forms.example/requisition' },
    ]}
  />))
  await act(async () => { await mappedApi.fetchMappedPageDataset.mock.results[0]?.value })
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 50)) })

  const buttons = () =>
    [...container.querySelectorAll('button, a.ant-btn')].map((button) => button.textContent)
  expect(buttons().some((label) => label?.includes('新增放置申请'))).toBe(true)
  expect(buttons().some((label) => label?.includes('新增领用申请'))).toBe(false)

  const placementLink = container.querySelector('a[href="https://forms.example/placement"]')
  expect(placementLink?.getAttribute('target')).toBe('_blank')
})
