/* @vitest-environment happy-dom */

import { act, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App, ConfigProvider } from 'antd'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { ValidationAuditFileListItem, ValidationAuditTask } from '@/types/validation-audit'
import ValidationAuditDetailClient from './ValidationAuditDetailClient'
import ValidationAuditNewClient from './ValidationAuditNewClient'

const mocks = vi.hoisted(() => ({
  create: vi.fn(), upload: vi.fn(), parse: vi.fn(), audit: vi.fn(), push: vi.fn(),
  task: vi.fn(), files: vi.fn(), issues: vi.fn(), report: vi.fn(),
}))
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: mocks.push }) }))
vi.mock('@/actions/validation-audit', () => ({
  createValidationAuditTask: mocks.create,
  uploadValidationAuditFiles: mocks.upload,
  parseValidationAuditFiles: mocks.parse,
  runValidationAudit: mocks.audit,
}))
vi.mock('@/lib/api/validation-audit', () => ({
  fetchValidationAuditTaskById: mocks.task,
  fetchValidationAuditFiles: mocks.files,
  fetchValidationAuditIssues: mocks.issues,
  fetchValidationAuditReport: mocks.report,
}))

const task: ValidationAuditTask = {
  id: 'audit-1', task_name: '验证审核', product_name: '示例产品', method_name: '示例方法',
  source_company: '质量部', audit_mode: 'protocol', status: 'uploaded', conclusion: null,
  risk_level: null, serious_count: 0, general_count: 0, suggestion_count: 0,
  compliant_count: 0, non_compliant_count: 0, report_path: null,
  created_at: '2026-08-01', updated_at: '2026-08-01',
}
const pending: ValidationAuditFileListItem = {
  id: 'file-1', file_type: 'protocol', original_filename: '原始方案.pdf', file_size: 100,
  parse_status: 'pending', created_at: '2026-08-01',
}
const denied = '没有执行此操作的权限，请联系管理员'
const internalError = 'TypeError: internal upload failure'
const succeeded = { filename: '方案.pdf', status: 'uploaded', file_id: 'file-2' }
const rejected = { filename: '补充.pdf', status: 'failed', status_code: 415 }

let host: HTMLDivElement
let root: Root

beforeEach(() => {
  vi.resetAllMocks()
  mocks.task.mockResolvedValue({ data: task })
  mocks.files.mockResolvedValue({ data: [] })
  mocks.issues.mockResolvedValue({ data: [] })
  mocks.report.mockResolvedValue({ data: null })
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
})

afterEach(async () => {
  await act(async () => root.unmount())
  host.remove()
})

async function render(node: ReactNode) {
  await act(async () => root.render(
    <ConfigProvider theme={{ token: { motion: false } }}><App>{node}</App></ConfigProvider>,
  ))
}

async function click(text: string) {
  const button = Array.from(host.querySelectorAll('button'))
    .find((el) => el.textContent?.replace(/\s/g, '') === text.replace(/\s/g, ''))
  expect(button).toBeDefined()
  await act(async () => button?.click())
}

async function selectFiles(...filenames: string[]) {
  const picker = host.querySelector<HTMLInputElement>('input[type="file"]')
  expect(picker).not.toBeNull()
  const files = filenames.map(name => new File(['audit fixture'], name, { type: 'application/pdf' }))
  Object.defineProperty(picker, 'files', { configurable: true, value: files })
  await act(async () => picker?.dispatchEvent(new Event('change', { bubbles: true })))
}

async function fillTaskFields() {
  await act(async () => {
    for (const field of ['task_name', 'product_name', 'method_name', 'source_company']) {
      const input = host.querySelector<HTMLInputElement>(`#${field}`)
      expect(input).not.toBeNull()
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(input, '验证用内容')
      input?.dispatchEvent(new Event('input', { bubbles: true }))
    }
  })
}

it('keeps the new task form and selected file after task creation is denied', async () => {
  mocks.create.mockResolvedValue({ ok: false, message: denied })
  await render(<ValidationAuditNewClient />)
  await fillTaskFields()
  await selectFiles('方案.pdf')
  await click('创建并开始审核')

  expect(mocks.create).toHaveBeenCalledWith(expect.objectContaining({ task_name: '验证用内容' }))
  expect(host.querySelector<HTMLInputElement>('#task_name')?.value).toBe('验证用内容')
  expect(host.textContent).toContain('方案.pdf')
  expect(document.body.textContent).toContain(denied)
  expect(mocks.upload).not.toHaveBeenCalled()
  expect(mocks.push).not.toHaveBeenCalled()
})

it.each([
  { title: 'complete success', result: [succeeded], notice: '任务创建成功' },
  { title: 'partial success', result: [succeeded, rejected], notice: '任务已创建。上传成功 1 个，失败 1 个' },
  { title: 'unconfirmed upload', result: null, notice: '任务已创建。暂未确认审核文件上传结果' },
])('opens the existing task after $title', async ({ result, notice }) => {
  mocks.create.mockResolvedValue({ ok: true, data: task })
  if (result) mocks.upload.mockResolvedValue({ ok: true, data: result })
  else mocks.upload.mockRejectedValue(new Error(internalError))
  await render(<ValidationAuditNewClient />)
  await fillTaskFields()
  await selectFiles('方案.pdf', '补充.pdf')
  await click('创建并开始审核')

  const [taskId, request] = mocks.upload.mock.calls[0] as [string, FormData]
  expect(taskId).toBe(task.id)
  expect(request.get('file_type')).toBe('protocol')
  expect(request.getAll('files')).toHaveLength(2)
  expect(mocks.push).toHaveBeenCalledWith(expect.stringContaining(`/registration/validation-audit/${task.id}`))
  expect(document.body.textContent).toContain(notice)
  expect(document.body.textContent).not.toContain(internalError)
})

it('keeps only failed files selected after a partial upload and allows retry', async () => {
  mocks.upload
    .mockResolvedValueOnce({ ok: true, data: [succeeded, rejected] })
    .mockRejectedValueOnce(new Error(internalError))
    .mockResolvedValueOnce({ ok: true, data: [{ ...succeeded, filename: rejected.filename }] })
  await render(<ValidationAuditDetailClient task={task} initialFiles={[]} initialIssues={[]} initialReport={null} />)
  await selectFiles('方案.pdf', '补充.pdf')
  await click('上传 (2)')
  expect(document.body.textContent).toContain('上传成功 1 个，失败 1 个')

  await click('上传 (1)')
  expect(document.body.textContent).toContain('暂未确认审核文件上传结果')
  expect(document.body.textContent).not.toContain(internalError)

  await click('上传 (1)')
  const [, retry] = mocks.upload.mock.lastCall as [string, FormData]
  expect(retry.getAll('files').map(file => (file as File).name)).toEqual(['补充.pdf'])
  expect(document.body.textContent).toContain('已上传 1 个文件')
})

it.each([
  ['开始解析', 'pending', 'parse', '文件解析完成'],
  ['开始审核', 'completed', 'audit', '审核完成'],
] as const)('preserves files after %s is denied and re-enables retry', async (label, status, action, success) => {
  const files = [{ ...pending, parse_status: status }]
  mocks.files.mockResolvedValue({ data: files })
  mocks[action].mockResolvedValueOnce({ ok: false, message: denied }).mockResolvedValueOnce({ ok: true, data: {} })
  await render(<ValidationAuditDetailClient task={task} initialFiles={files} initialIssues={[]} initialReport={null} />)

  await click(label)
  expect(document.body.textContent).toContain(denied)
  expect(host.textContent).toContain(pending.original_filename)
  await click(label)
  expect(mocks[action]).toHaveBeenCalledTimes(2)
  expect(document.body.textContent).toContain(success)
})
