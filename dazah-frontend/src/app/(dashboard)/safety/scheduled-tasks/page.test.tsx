import { describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ getScheduledTasks: vi.fn() }))
vi.mock('@/actions/safety', () => ({ getScheduledTasks: mocks.getScheduledTasks }))
vi.mock('@/components/safety', () => ({ ScheduledTaskList: () => null }))

import ScheduledTasksPage from './page'

describe('scheduled tasks list URL', () => {
  it('loads the requested page and size after returning from detail', async () => {
    mocks.getScheduledTasks.mockResolvedValue({ data: [], meta: { total: 48 } })
    await ScheduledTasksPage({ searchParams: Promise.resolve({ page: '3', page_size: '10' }) })
    expect(mocks.getScheduledTasks).toHaveBeenCalledWith({ page: 3, page_size: 10 })
  })
})
