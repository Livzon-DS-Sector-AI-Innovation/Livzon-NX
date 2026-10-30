/* @vitest-environment happy-dom */

import { act, createElement, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true })

const mocks = vi.hoisted(() => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  canOperate: true,
  canDelete: true,
  getHazardousChemicals: vi.fn(),
  createHazardousChemical: vi.fn(),
  updateHazardousChemical: vi.fn(),
  deleteHazardousChemical: vi.fn(),
  listChemicalMsdsFiles: vi.fn(),
  uploadChemicalMsdsFile: vi.fn(),
  deleteChemicalMsdsFile: vi.fn(),
  reextractChemicalMsdsFile: vi.fn(),
  fetchChemicalMsdsBytes: vi.fn(),
}))

vi.mock('@/actions/safety', () => ({
  getHazardousChemicals: mocks.getHazardousChemicals,
  createHazardousChemical: mocks.createHazardousChemical,
  updateHazardousChemical: mocks.updateHazardousChemical,
  deleteHazardousChemical: mocks.deleteHazardousChemical,
  listChemicalMsdsFiles: mocks.listChemicalMsdsFiles,
  uploadChemicalMsdsFile: mocks.uploadChemicalMsdsFile,
  deleteChemicalMsdsFile: mocks.deleteChemicalMsdsFile,
  reextractChemicalMsdsFile: mocks.reextractChemicalMsdsFile,
  fetchChemicalMsdsBytes: mocks.fetchChemicalMsdsBytes,
}))

vi.mock('@/hooks/usePagePermissions', () => ({
  usePagePermissions: () => ({
    canAccess: true,
    canQuery: true,
    canOperate: mocks.canOperate,
    canDelete: mocks.canDelete,
  }),
}))

vi.mock('./PageFeishuTable', () => ({
  default: () =>
    createElement('div', { 'data-mirror-table': 'y' }, '危化品统计表镜像'),
}))

vi.mock('@/components/quality', () => ({
  FeishuAttachmentPreviewModal: ({
    open,
    fileName,
  }: {
    open?: boolean
    fileName?: string
  }) =>
    open
      ? createElement('div', { 'data-preview-modal': 'y' }, fileName ?? '')
      : null,
}))

vi.mock('@ant-design/icons', () => {
  const Icon = () => null
  return {
    DeleteOutlined: Icon,
    DownloadOutlined: Icon,
    EyeOutlined: Icon,
    FileTextOutlined: Icon,
    RobotOutlined: Icon,
    UploadOutlined: Icon,
  }
})

vi.mock('antd', async () => {
  const { createElement } = await import('react')
  type AnyProps = Record<string, unknown>
  interface Column {
    title?: unknown
    dataIndex?: string
    render?: (value: unknown, row: Record<string, unknown>) => ReactNode
  }
  const Box = ({ children, title }: AnyProps) =>
    createElement('div', null, title as ReactNode, children as ReactNode)
  const Button = ({ children, onClick, disabled, icon }: AnyProps) =>
    createElement(
      'button',
      {
        type: 'button',
        disabled: Boolean(disabled),
        'data-icon': icon ? 'y' : 'n',
        onClick: onClick as never,
      },
      children as ReactNode
    )
  const Table = ({
    columns,
    dataSource,
  }: {
    columns?: Column[]
    dataSource?: Array<Record<string, unknown>>
  }) =>
    createElement(
      'tbody',
      null,
      (dataSource ?? []).map((row, rowIndex) =>
        createElement(
          'tr',
          { key: String(row.id ?? rowIndex), 'data-row': String(row.id ?? rowIndex) },
          (columns ?? []).map((column, columnIndex) =>
            createElement(
              'td',
              { key: column.dataIndex ?? columnIndex },
              column.render
                ? (column.render(row[column.dataIndex ?? ''], row) as ReactNode)
                : ((row[column.dataIndex ?? ''] as ReactNode) ?? null)
            )
          )
        )
      )
    )
  const Tabs = ({
    items,
    activeKey,
    onChange,
  }: {
    items?: Array<{ key: string; label: string; children: ReactNode }>
    activeKey?: string
    onChange?: (key: string) => void
  }) =>
    createElement(
      'div',
      { 'data-active-tab': String(activeKey ?? '') },
      ...(items ?? []).map((item) =>
        createElement(
          'button',
          {
            key: item.key,
            type: 'button',
            'data-tab': item.key,
            onClick: () => (onChange as (key: string) => void)?.(item.key),
          },
          item.label
        )
      ),
      (items ?? []).find((item) => item.key === activeKey)?.children ?? null
    )
  const Input = Object.assign(() => createElement('input'), {
    Search: ({ placeholder, onSearch }: AnyProps) =>
      createElement(
        'button',
        {
          type: 'button',
          'data-search': String(placeholder ?? ''),
          onClick: () => (onSearch as (v: string) => void)?.(''),
        },
        'search'
      ),
    TextArea: (props: AnyProps) =>
      createElement('textarea', { placeholder: String(props.placeholder ?? '') }),
  })
  const formValues = {
    name: '乙醇',
    alias: '',
    cas_no: '',
    category: 'flammable_liquid',
    hazard_statements: '',
    storage_requirements: '',
    remark: '',
  }
  const useForm = () => [
    {
      setFieldsValue: vi.fn(),
      validateFields: vi.fn(async () => formValues),
    },
  ]
  const Form = Object.assign(
    ({ children }: AnyProps) => createElement('form', null, children as ReactNode),
    {
      useForm,
      Item: ({ children, label }: AnyProps) =>
        createElement(
          'div',
          null,
          label ? createElement('span', null, label as ReactNode) : null,
          children as ReactNode
        ),
    }
  )
  const Upload = ({ children, beforeUpload }: AnyProps) =>
    createElement(
      'span',
      null,
      children as ReactNode,
      beforeUpload
        ? createElement(
            'button',
            {
              type: 'button',
              'data-upload-trigger': 'y',
              onClick: () => {
                ;(beforeUpload as (file: File) => unknown)(
                  new File(['x'], '丙酮MSDS.pdf', { type: 'application/pdf' })
                )
              },
            },
            'trigger-upload'
          )
        : null
    )
  const Text = ({ children }: AnyProps) =>
    createElement('span', null, children as ReactNode)
  const App = Object.assign(
    ({ children }: AnyProps) => createElement('div', null, children as ReactNode),
    { useApp: () => ({ message: mocks.message }) }
  )
  const Meta = ({ title, description }: AnyProps) => {
    const titleText = String(
      (title as { props?: { children?: unknown } } | undefined)?.props?.children ?? ''
    )
    const descriptionText = String(
      (description as { props?: { children?: unknown } } | undefined)?.props
        ?.children ?? ''
    )
    return createElement(
      'div',
      { 'data-file-name': titleText },
      titleText,
      ' ',
      descriptionText
    )
  }
  const ListItem = ({ children, actions }: AnyProps) =>
    createElement(
      'div',
      { 'data-msds-item': 'y' },
      children as ReactNode,
      ...((actions as ReactNode[]) ?? [])
    )
  ListItem.Meta = Meta

  return {
    App,
    Button,
    Card: Box,
    Form,
    Input,
    List: Object.assign(
      ({ dataSource, renderItem }: AnyProps) =>
        createElement(
          'div',
          { 'data-msds-list': 'y' },
          ...(((dataSource ?? []) as Array<Record<string, unknown>>).map((file) =>
            (renderItem as (row: Record<string, unknown>) => ReactNode)(file)
          ) as ReactNode[])
        ),
      { Item: ListItem }
    ),
    Modal: ({ children, open, onOk, title, footer }: AnyProps) =>
      open
        ? createElement(
            'div',
            { 'data-modal-title': String(title ?? ''), 'data-modal-open': 'true' },
            children as ReactNode,
            (footer as ReactNode) ?? null,
            onOk
              ? createElement(
                  'button',
                  {
                    type: 'button',
                    'data-modal-ok': 'y',
                    onClick: onOk as never,
                  },
                  '确定'
                )
              : null
          )
        : null,
    Popconfirm: ({ children, onConfirm }: AnyProps) =>
      createElement(
        'span',
        null,
        children as ReactNode,
        onConfirm
          ? createElement(
              'button',
              {
                type: 'button',
                'data-popconfirm-ok': 'y',
                onClick: onConfirm as never,
              },
              '确认删'
            )
          : null
      ),
    Select: () => createElement('select'),
    Space: Box,
    Table,
    Tabs,
    Tag: ({ children }: AnyProps) =>
      createElement('span', null, children as ReactNode),
    Typography: Object.assign(
      ({ children }: AnyProps) => createElement('div', null, children as ReactNode),
      { Text, Title: Text }
    ),
    Upload,
  }
})

import HazchemPanel from './HazchemPanel'

const PAGE_KEY = 'safety:site-mgmt:hazchem-msds'

const CHEMICALS = [
  {
    id: 'c-1',
    name: '乙醇',
    alias: '酒精',
    cas_no: '64-17-5',
    category: 'flammable_liquid',
    hazard_statements: '高度易燃液体',
    storage_requirements: '阴凉通风',
    msds_file_path: '',
    msds_file_name: '',
    remark: '',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
]

const MSDS_FILES = [
  {
    id: 'f-1',
    chemical_id: 'c-1',
    file_name: '乙醇MSDS.pdf',
    content_type: 'application/pdf',
    size_bytes: 2048,
    created_at: '2026-10-01T00:00:00Z',
    created_by: null,
  },
]

const UPLOAD_WITH_AI = {
  code: 200,
  data: {
    file: MSDS_FILES[0],
    chemical: CHEMICALS[0],
    ai_suggestion: {
      name: '丙酮',
      alias: null,
      cas_no: '67-64-1',
      category: 'flammable_liquid',
      category_label: '易燃液体',
      hazard_statements: '高度易燃液体和蒸气',
      storage_requirements: null,
      remark: null,
    },
    ai_error: null,
  },
}

let root: Root | null = null
let container: HTMLElement

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  mocks.canOperate = true
  mocks.canDelete = true
  mocks.listChemicalMsdsFiles.mockResolvedValue({
    code: 200,
    data: { items: MSDS_FILES },
  })
})

afterEach(() => {
  root?.unmount()
  root = null
  container.remove()
  vi.clearAllMocks()
})

async function renderPanel(overrides: Record<string, unknown> = {}) {
  root = createRoot(container)
  await act(async () => {
    root!.render(
      createElement(HazchemPanel, {
        pageKey: PAGE_KEY,
        initialChemicals: CHEMICALS,
        initialError: null,
        ...overrides,
      })
    )
  })
}

function findButton(text: string) {
  return [...container.querySelectorAll<HTMLButtonElement>('button')].find(
    (button) => button.textContent?.includes(text)
  )
}

async function openMsdsManager() {
  await act(async () => {
    findButton('查看 / 上传')!.click()
    await new Promise((resolve) => setTimeout(resolve, 30))
  })
  const modal = container.querySelector('[data-modal-title^="MSDS 附件"]')
  expect(modal).not.toBeNull()
  return modal as HTMLElement
}

describe('HazchemPanel', () => {
  it('renders chemical catalog with MSDS entry and lazy mirror tab', async () => {
    await renderPanel()
    const markup = container.innerHTML
    expect(markup).toContain('危化品与 MSDS 管理')
    expect(container.querySelector('[data-row="c-1"]')).not.toBeNull()
    expect(markup).toContain('乙醇')
    expect(markup).toContain('64-17-5')
    expect(findButton('查看 / 上传')).toBeDefined()
    // 镜像表初始不挂载，切到页签后挂载
    expect(container.querySelector('[data-mirror-table]')).toBeNull()
    const inventoryTab = container.querySelector<HTMLButtonElement>(
      'button[data-tab="inventory"]'
    )
    expect(inventoryTab).not.toBeNull()
    await act(async () => {
      inventoryTab!.click()
    })
    expect(container.querySelector('[data-mirror-table]')).not.toBeNull()
  })

  it('opens MSDS manager, lists files and downloads', async () => {
    mocks.fetchChemicalMsdsBytes.mockResolvedValue({
      base64: Buffer.from('pdf').toString('base64'),
      contentType: 'application/pdf',
    })
    await renderPanel()
    const msdsModal = await openMsdsManager()
    expect(mocks.listChemicalMsdsFiles).toHaveBeenCalledWith('c-1')
    expect(msdsModal.textContent).toContain('乙醇MSDS.pdf')
    const download = [...msdsModal.querySelectorAll<HTMLButtonElement>('button')].find(
      (button) => button.textContent === '下载'
    )
    expect(download).toBeDefined()
    await act(async () => {
      download!.click()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    expect(mocks.fetchChemicalMsdsBytes).toHaveBeenCalledWith('c-1', 'f-1', false)
  })

  it('previews MSDS through object URLs', async () => {
    mocks.fetchChemicalMsdsBytes.mockResolvedValue({
      base64: Buffer.from('pdf').toString('base64'),
      contentType: 'application/pdf',
    })
    await renderPanel()
    const msdsModal = await openMsdsManager()
    const preview = [...msdsModal.querySelectorAll<HTMLButtonElement>('button')].find(
      (button) => button.textContent === '预览'
    )
    expect(preview).toBeDefined()
    await act(async () => {
      preview!.click()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    expect(mocks.fetchChemicalMsdsBytes).toHaveBeenCalledWith('c-1', 'f-1', true)
    expect(mocks.fetchChemicalMsdsBytes).toHaveBeenCalledWith('c-1', 'f-1', false)
    expect(container.querySelector('[data-preview-modal]')).not.toBeNull()
  })

  it('upload with AI suggestion opens confirm modal and applies to archive', async () => {
    mocks.uploadChemicalMsdsFile.mockResolvedValue(UPLOAD_WITH_AI)
    mocks.updateHazardousChemical.mockResolvedValue({
      code: 200,
      message: 'success',
      data: null,
    })
    mocks.getHazardousChemicals.mockResolvedValue({
      code: 200,
      data: { items: CHEMICALS, total: 1 },
    })
    await renderPanel()
    const msdsModal = await openMsdsManager()
    const trigger = msdsModal.querySelector<HTMLButtonElement>(
      '[data-upload-trigger]'
    )
    expect(trigger).toBeDefined()
    await act(async () => {
      trigger!.click()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    expect(mocks.uploadChemicalMsdsFile).toHaveBeenCalledWith(
      'c-1',
      expect.objectContaining({ name: '丙酮MSDS.pdf' })
    )
    const aiModal = container.querySelector(
      '[data-modal-title="AI 识别结果确认"]'
    )
    expect(aiModal).not.toBeNull()
    const ok = aiModal!.querySelector<HTMLButtonElement>('[data-modal-ok]')
    expect(ok).not.toBeNull()
    await act(async () => {
      ok!.click()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    expect(mocks.updateHazardousChemical).toHaveBeenCalledWith('c-1', {
      name: '乙醇',
      alias: '',
      cas_no: '',
      category: 'flammable_liquid',
      hazard_statements: '',
      storage_requirements: '',
      remark: '',
    })
  })

  it('upload without AI suggestion keeps archive untouched', async () => {
    mocks.uploadChemicalMsdsFile.mockResolvedValue({
      code: 200,
      data: { file: MSDS_FILES[0], chemical: CHEMICALS[0], ai_suggestion: null, ai_error: '平台未配置 AI 模型，无法自动识别' },
    })
    await renderPanel()
    const msdsModal = await openMsdsManager()
    const trigger = msdsModal.querySelector<HTMLButtonElement>(
      '[data-upload-trigger]'
    )
    await act(async () => {
      trigger!.click()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    expect(
      container.querySelector('[data-modal-title="AI 识别结果确认"]')
    ).toBeNull()
    expect(mocks.updateHazardousChemical).not.toHaveBeenCalled()
    expect(mocks.message.info).toHaveBeenCalled()
  })

  it('deletes an MSDS attachment after confirmation', async () => {
    mocks.deleteChemicalMsdsFile.mockResolvedValue({ code: 200, data: null })
    await renderPanel()
    const msdsModal = await openMsdsManager()
    const confirm = msdsModal.querySelector<HTMLButtonElement>(
      '[data-popconfirm-ok]'
    )
    expect(confirm).toBeDefined()
    await act(async () => {
      confirm!.click()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    expect(mocks.deleteChemicalMsdsFile).toHaveBeenCalledWith('c-1', 'f-1')
  })

  it('disables create button without operate permission', async () => {
    mocks.canOperate = false
    await renderPanel()
    const createButton = findButton('新增危化品')
    expect(createButton).toBeDefined()
    expect(createButton!.disabled).toBe(true)
  })

  it('creates a chemical through the modal submit', async () => {
    mocks.createHazardousChemical.mockResolvedValue({
      code: 200,
      message: 'success',
      data: null,
    })
    await renderPanel()
    await act(async () => {
      findButton('新增危化品')!.click()
    })
    const modal = container.querySelector('[data-modal-open="true"]')
    expect(modal).not.toBeNull()
    const ok = modal!.querySelector<HTMLButtonElement>('[data-modal-ok]')
    await act(async () => {
      ok!.click()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    expect(mocks.createHazardousChemical).toHaveBeenCalled()
  })

  it('删除危化品档案（Popconfirm 确认后调用）', async () => {
    mocks.deleteHazardousChemical.mockResolvedValue({
      code: 200,
      message: 'success',
      data: null,
    })
    await renderPanel()
    const confirm = container.querySelector<HTMLButtonElement>(
      '[data-popconfirm-ok]'
    )
    expect(confirm).toBeDefined()
    await act(async () => {
      confirm!.click()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    expect(mocks.deleteHazardousChemical).toHaveBeenCalled()
  })

  it('MSDS 上传失败提示错误', async () => {
    mocks.uploadChemicalMsdsFile.mockResolvedValue({
      code: 500,
      message: '附件保存失败',
    })
    await renderPanel()
    const msdsModal = await openMsdsManager()
    const trigger = msdsModal.querySelector<HTMLButtonElement>(
      '[data-upload-trigger]'
    )
    expect(trigger).toBeDefined()
    await act(async () => {
      trigger!.click()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    expect(mocks.message.error).toHaveBeenCalledWith('附件保存失败')
  })

  it('MSDS 下载失败提示错误', async () => {
    mocks.fetchChemicalMsdsBytes.mockRejectedValue(new Error('网络中断'))
    await renderPanel()
    const msdsModal = await openMsdsManager()
    const download = [...msdsModal.querySelectorAll<HTMLButtonElement>('button')].find(
      (button) => button.textContent === '下载'
    )
    await act(async () => {
      download!.click()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    expect(mocks.message.error).toHaveBeenCalledWith('网络中断')
  })

  it('MSDS 重新识别失败提示错误', async () => {
    mocks.reextractChemicalMsdsFile.mockResolvedValue({
      code: 500,
      message: '识别服务不可用',
    })
    await renderPanel()
    const msdsModal = await openMsdsManager()
    const extract = [...msdsModal.querySelectorAll<HTMLButtonElement>('button')].find(
      (button) => button.textContent?.includes('重新识别')
    )
    expect(extract).toBeDefined()
    await act(async () => {
      extract!.click()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    expect(mocks.message.error).toHaveBeenCalledWith('识别服务不可用')
  })
})
