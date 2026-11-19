import { beforeEach, expect, it, vi } from 'vitest'

const calls = vi.hoisted(() => ({
  task: vi.fn(), files: vi.fn(), issues: vi.fn(), report: vi.fn(),
  notFound: vi.fn(() => { throw new Error('not found') }),
}))
vi.mock('next/navigation', () => ({ notFound: calls.notFound }))
vi.mock('@/actions/validation-audit', () => ({
  fetchTaskByIdServer: calls.task, fetchFilesServer: calls.files,
  fetchIssuesServer: calls.issues, fetchReportServer: calls.report,
}))
vi.mock('@/components/registration/validation-audit', () => ({ ValidationAuditDetailClient: () => null }))

import ValidationAuditDetailPage from './page'

const task = { id: 'audit-1' }
const input = { params: Promise.resolve({ id: task.id }) }
const denied = '没有执行此操作的权限，请联系管理员'

beforeEach(() => {
  vi.resetAllMocks()
  calls.task.mockResolvedValue({ ok: true, data: { data: task } })
  calls.files.mockResolvedValue({ ok: true, data: { data: [] } })
  calls.issues.mockResolvedValue({ ok: true, data: { data: [] } })
  calls.report.mockResolvedValue({ ok: true, data: null })
})

it.each([
  ['task', '无法加载审核任务'],
  ['files', '无法加载审核文件'],
  ['issues', '无法加载审核问题'],
  ['report', '无法加载审核报告'],
] as const)('reports a denied %s read instead of displaying empty data', async (reader, title) => {
  calls[reader].mockResolvedValue({ ok: false, message: denied })
  const page = await ValidationAuditDetailPage(input)
  expect(page.props).toMatchObject({ status: 'error', title, subTitle: denied })
  expect(calls[reader]).toHaveBeenCalledWith(task.id)
  expect(calls.notFound).not.toHaveBeenCalled()
  if (reader === 'task') expect(calls.files).not.toHaveBeenCalled()
})

it('uses notFound only for an absent task and accepts an absent report', async () => {
  calls.task.mockResolvedValueOnce({ ok: true, data: null })
  await expect(ValidationAuditDetailPage(input)).rejects.toThrow('not found')
  expect(calls.files).not.toHaveBeenCalled()

  const page = await ValidationAuditDetailPage(input)
  expect(page.props).toEqual({ task, initialFiles: [], initialIssues: [], initialReport: null })
})
