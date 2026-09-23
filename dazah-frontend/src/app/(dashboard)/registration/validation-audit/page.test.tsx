import { describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ fetchTasksServer: vi.fn() }))
vi.mock('@/actions/validation-audit', () => ({ fetchTasksServer: mocks.fetchTasksServer }))
vi.mock('@/components/registration/validation-audit', () => ({ ValidationAuditListClient: () => null }))

import ValidationAuditPage from './page'

describe('validation audit list URL', () => {
  it('restores requested pagination and falls back for invalid values', async () => {
    mocks.fetchTasksServer.mockResolvedValue({ data: { items: [], total: 0 } })
    await ValidationAuditPage({ searchParams: Promise.resolve({ page: '4', page_size: '50' }) })
    expect(mocks.fetchTasksServer).toHaveBeenLastCalledWith({ page: 4, page_size: 50 })
    await ValidationAuditPage({ searchParams: Promise.resolve({ page: '-1', page_size: '9999' }) })
    expect(mocks.fetchTasksServer).toHaveBeenLastCalledWith({ page: 1, page_size: 20 })
  })
})
