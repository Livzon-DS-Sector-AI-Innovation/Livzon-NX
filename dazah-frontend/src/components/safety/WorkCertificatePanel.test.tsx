/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getWorkCertificates: vi.fn(),
  getCertificateExpirySummary: vi.fn(),
  getCertificateCategories: vi.fn(),
  createWorkCertificate: vi.fn(),
  updateWorkCertificate: vi.fn(),
  deleteWorkCertificate: vi.fn(),
  uploadWorkCertificateFile: vi.fn(),
  canOperate: true,
  canDelete: true,
  canAccess: true,
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

vi.mock('@/actions/safety', () => ({
  getWorkCertificates: mocks.getWorkCertificates,
  getCertificateExpirySummary: mocks.getCertificateExpirySummary,
  getCertificateCategories: mocks.getCertificateCategories,
  createWorkCertificate: mocks.createWorkCertificate,
  updateWorkCertificate: mocks.updateWorkCertificate,
  deleteWorkCertificate: mocks.deleteWorkCertificate,
  uploadWorkCertificateFile: mocks.uploadWorkCertificateFile,
}))

vi.mock('@/hooks/usePagePermissions', () => ({
  usePagePermissions: () => ({
    canAccess: mocks.canAccess,
    canQuery: mocks.canAccess,
    canOperate: mocks.canOperate,
    canDelete: mocks.canDelete,
    canApprove: true,
    canReject: true,
  }),
}))

vi.mock('@/components/safety/WorkCertificateImportModal', () => ({
  default: () => null,
}))

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>()
  const { createElement } = await import('react')
  const DatePickerStub = (props: Record<string, unknown>) =>
    createElement('input', {
      'data-testid': 'date-picker-stub',
      value: (props.value as string) ?? '',
      onChange: props.onChange,
    })
  // antd v6 的 Upload 内部结构在 happy-dom 下无法从 DOM 触达，
  // 用探测按钮直调其 onChange，专测面板自身的选择→上传接线
  const UploadStub = (props: Record<string, unknown>) =>
    createElement(
      'span',
      null,
      props.children as never,
      createElement(
        'button',
        {
          type: 'button',
          'data-testid': 'upload-probe',
          onClick: () =>
            (
              props as {
                onChange?: (info: unknown) => void
              }
            ).onChange?.({
              file: {
                uid: 'u-probe',
                name: 'probe.pdf',
                originFileObj: new File(['x'], 'probe.pdf', {
                  type: 'application/pdf',
                }),
              },
              fileList: [],
            }),
        },
        'probe-upload',
      ),
    )
  return {
    ...actual,
    DatePicker: Object.assign(DatePickerStub, { RangePicker: DatePickerStub }),
    Upload: UploadStub,
    message: mocks.message,
  }
})

vi.mock('@ant-design/icons', () => {
  const Icon = () => null
  return { ImportOutlined: Icon, ArrowUpOutlined: Icon }
})

import { WorkCertificatePanel } from './WorkCertificatePanel'

const SUMMARY = { total: 2, expiring_in_30d: 1, expired: 1 }

const ROWS = [
  {
    id: 'cert1',
    person_name: '张三',
    department: '维修班',
    certificate_category: 'electrician',
    certificate_category_label: '电工',
    certificate_no: 'DJ-001',
    issuing_authority: '应急管理局',
    issue_date: '2024-01-01',
    expiry_date: null,
    qualification_scope: null,
    status: 'valid',
    files: [],
    days_to_expiry: null,
  },
  {
    id: 'cert2',
    person_name: '李四',
    department: null,
    certificate_category: 'forklift',
    certificate_category_label: '叉车',
    certificate_no: 'CC-002',
    issuing_authority: null,
    issue_date: null,
    expiry_date: '2026-11-20',
    qualification_scope: null,
    status: 'expiring',
    files: [{ id: 'f1', file_name: '证.jpg' }],
    days_to_expiry: 12,
  },
]

let root: Root | undefined

function flush(ms = 60) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function buttons(text: string) {
  return Array.from(
    document.body.querySelectorAll<HTMLButtonElement>('button'),
  ).filter((b) => b.textContent?.replace(/\s/g, '').includes(text))
}

async function setInputValue(node: HTMLInputElement, value: string) {
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(
      node,
      value,
    )
    node.dispatchEvent(new Event('input', { bubbles: true }))
  })
}

async function triggerUpload() {
  const probe = document.body.querySelector<HTMLButtonElement>(
    'button[data-testid="upload-probe"]',
  )
  expect(probe, 'Upload 探测按钮应存在').toBeTruthy()
  await act(async () => {
    probe!.click()
  })
}

beforeEach(() => {
  mocks.getWorkCertificates.mockResolvedValue({
    code: 200,
    data: { items: ROWS, total: ROWS.length },
  })
  mocks.getCertificateExpirySummary.mockResolvedValue({
    code: 200,
    data: SUMMARY,
  })
  mocks.getCertificateCategories.mockResolvedValue({
    code: 200,
    data: { categories: [{ value: 'electrician', label: '电工' }] },
  })
  mocks.createWorkCertificate.mockResolvedValue({ code: 200, data: { id: 'n1' } })
  mocks.updateWorkCertificate.mockResolvedValue({ code: 200, data: { id: 'c1' } })
  mocks.deleteWorkCertificate.mockResolvedValue({ code: 200, data: null })
})

afterEach(async () => {
  if (root) {
    await act(async () => {
      root!.unmount()
    })
    root = undefined
  }
  document.body.replaceChildren()
  vi.clearAllMocks()
})

async function renderPanel(props: Record<string, unknown> = {}) {
  const container = document.body.appendChild(document.createElement('div'))
  await act(async () => {
    root = createRoot(container)
    root!.render(
      <WorkCertificatePanel
        {...({
          initialList: { items: ROWS, total: ROWS.length },
          initialSummary: SUMMARY,
          initialError: null,
          ...props,
        } as unknown as React.ComponentProps<typeof WorkCertificatePanel>)}
      />,
    )
  })
  await flush()
}

describe('证件管理面板', () => {
  it('渲染统计卡、证件列表与附件预览链接', async () => {
    await renderPanel()
    expect(document.body.textContent).toContain('全部：2')
    expect(document.body.textContent).toContain('30天内到期：1')
    expect(document.body.textContent).toContain('已过期：1')
    expect(document.body.textContent).toContain('张三')
    expect(document.body.textContent).toContain('12天')
    expect(
      Array.from(document.body.querySelectorAll('a')).some((a) =>
        (a.getAttribute('href') ?? '').endsWith('/files/f1/preview'),
      ),
    ).toBe(true)
  })

  it('点击状态统计卡按状态重新加载', async () => {
    await renderPanel()
    await act(async () => {
      buttons('30天内到期')[0].click()
    })
    await flush()
    expect(mocks.getWorkCertificates).toHaveBeenLastCalledWith(
      expect.objectContaining({ status: 'expiring' }),
    )
  })

  it('关键词搜索触发按条件加载', async () => {
    await renderPanel()
    const input = document.body.querySelector<HTMLInputElement>(
      'input[placeholder="姓名/证件号/部门"]',
    )
    expect(input).toBeTruthy()
    await setInputValue(input!, '张三')
    // antd v6 搜索按钮无稳定文案类名：直接回车触发 onSearch
    await act(async () => {
      input!.dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }),
      )
    })
    await flush()
    expect(mocks.getWorkCertificates).toHaveBeenLastCalledWith(
      expect.objectContaining({ keyword: '张三' }),
    )
  })

  it('新建证件：填写并选择类别后创建成功', async () => {
    await renderPanel()
    await act(async () => {
      buttons('新建证件')[0].click()
    })
    await flush()
    expect(document.body.textContent).toContain('新建证件')
    const name = document.body.querySelector<HTMLInputElement>(
      'input[placeholder="持证人姓名"], input[id*="person_name"]',
    )
    const formNameInput = Array.from(
      document.body.querySelectorAll<HTMLInputElement>('input'),
    ).find((n) => n.id.includes('person_name'))
    const target = name ?? formNameInput
    expect(target).toBeTruthy()
    await setInputValue(target!, '王五')
    // 选择类别：antd v6 对 .ant-select-input 派发 mousedown 打开下拉
    const categoryInput = document.body.querySelector<HTMLElement>(
      'input#certificate_category',
    )
    expect(categoryInput).toBeTruthy()
    await act(async () => {
      categoryInput!.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
    })
    await flush(40)
    const option = Array.from(
      document.body.querySelectorAll<HTMLDivElement>('.ant-select-item-option'),
    ).find((o) => o.textContent?.includes('电工'))
    expect(option, '类别下拉应出现电工选项').toBeTruthy()
    await act(async () => {
      option!.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      option!.click()
    })
    await flush(30)
    await act(async () => {
      buttons('保存')[0].click()
    })
    await flush()
    expect(mocks.createWorkCertificate).toHaveBeenCalledWith(
      expect.objectContaining({
        person_name: '王五',
        certificate_category: 'electrician',
      }),
    )
    expect(mocks.message.success).toHaveBeenCalledWith('证件已创建')
  })

  it('编辑证件：回填并提交更新', async () => {
    await renderPanel()
    await act(async () => {
      const edit = Array.from(document.body.querySelectorAll('a')).find(
        (a) => a.textContent === '编辑',
      )
      edit!.click()
    })
    await flush()
    expect(document.body.textContent).toContain('编辑证件：张三')
    const prefilled = Array.from(
      document.body.querySelectorAll<HTMLInputElement>('input'),
    ).find((n) => n.id.includes('person_name'))
    expect(prefilled?.value).toBe('张三')
    await act(async () => {
      buttons('保存')[0].click()
    })
    await flush()
    expect(mocks.updateWorkCertificate).toHaveBeenCalledWith(
      'cert1',
      expect.objectContaining({ person_name: '张三', certificate_no: 'DJ-001' }),
    )
    expect(mocks.message.success).toHaveBeenCalledWith('证件已更新')
  })

  it('删除证件需 Popconfirm 确认', async () => {
    await renderPanel()
    await act(async () => {
      const del = Array.from(document.body.querySelectorAll('a')).find(
        (a) => a.textContent === '删除',
      )
      del!.click()
    })
    await flush()
    const ok = buttons('OK')
    expect(ok.length).toBeGreaterThan(0)
    await act(async () => {
      ok[ok.length - 1].click()
    })
    await flush()
    expect(mocks.deleteWorkCertificate).toHaveBeenCalledWith('cert1')
    expect(mocks.message.success).toHaveBeenCalledWith('已删除')
  })

  it('上传附件带 AI 识别建议：确认后回填', async () => {
    mocks.uploadWorkCertificateFile.mockResolvedValue({
      code: 200,
      data: {
        ai_suggestion: {
          person_name: '赵六',
          certificate_category: 'electrician',
          certificate_no: 'DJ-009',
        },
        ai_error: null,
      },
    })
    await renderPanel()
    await act(async () => {
      const edit = Array.from(document.body.querySelectorAll('a')).find(
        (a) => a.textContent === '编辑',
      )
      edit!.click()
    })
    await flush()
    await triggerUpload()
    await flush()
    expect(mocks.uploadWorkCertificateFile).toHaveBeenCalledWith(
      'cert1',
      expect.anything(),
    )
    expect(document.body.textContent).toContain('确认 AI 识别结果')
    const ok = buttons('已核对')
    expect(ok.length).toBeGreaterThan(0)
    await act(async () => {
      ok[0].click()
    })
    await flush()
    expect(mocks.message.success).toHaveBeenCalledWith(
      '识别内容已回填表单，请核对后保存',
    )
  })

  it('上传识别失败提示警告', async () => {
    mocks.uploadWorkCertificateFile.mockResolvedValue({
      code: 200,
      data: { ai_suggestion: null, ai_error: '照片模糊' },
    })
    await renderPanel()
    await act(async () => {
      const edit = Array.from(document.body.querySelectorAll('a')).find(
        (a) => a.textContent === '编辑',
      )
      edit!.click()
    })
    await flush()
    await triggerUpload()
    await flush()
    expect(mocks.message.warning).toHaveBeenCalledWith('照片模糊')
  })
})
