import { describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ fetchTasksServer: vi.fn() }))
vi.mock('@/actions/validation-audit', () => ({ fetchTasksServer: mocks.fetchTasksServer }))
vi.mock('@/components/registration/validation-audit', () => ({ ValidationAuditListClient: () => null }))

import ValidationAuditPage from './page'

describe('validation audit list URL', () => {
  it('restores requested pagination and falls back for invalid values', async () => {
    mocks.fetchTasksServer.mockResolvedValue({ ok: true, data: { data: { items: [], total: 0 } } })
    await ValidationAuditPage({ searchParams: Promise.resolve({ page: '4', page_size: '50' }) })
    expect(mocks.fetchTasksServer).toHaveBeenLastCalledWith({ page: 4, page_size: 50 })
    await ValidationAuditPage({ searchParams: Promise.resolve({ page: '-1', page_size: '9999' }) })
    expect(mocks.fetchTasksServer).toHaveBeenLastCalledWith({ page: 1, page_size: 20 })
  })

  it('shows access feedback instead of rendering an empty task list', async () => {
    mocks.fetchTasksServer.mockResolvedValue({ ok: false, message: '没有执行此操作的权限，请联系管理员' })
    const output = await ValidationAuditPage({ searchParams: Promise.resolve({}) })
    expect(output.props.subTitle).toBe('没有执行此操作的权限，请联系管理员')
  })
})
