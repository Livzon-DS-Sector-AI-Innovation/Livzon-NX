import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getServerApiBaseUrl: vi.fn(() => 'http://backend.test'),
  revalidatePath: vi.fn(),
}))

vi.mock('@/lib/server-api', () => ({ getServerApiBaseUrl: mocks.getServerApiBaseUrl }))
vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidatePath }))

import { createValidationAuditTask, deleteValidationAuditTask } from './validation-audit'

describe('validation audit server actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('creates and deletes audit tasks through the registration audit API', async () => {
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(async () =>
        new Response(JSON.stringify({ message: '创建成功', data: { id: 'task-1' } }), {
          status: 200,
        }),
      )
      .mockImplementationOnce(async () =>
        new Response(JSON.stringify({ message: '删除成功' }), { status: 200 }),
      )
    vi.stubGlobal('fetch', fetchMock)

    await expect(createValidationAuditTask({ product_name: '产品A' } as never)).resolves.toEqual({
      success: true,
      message: '创建成功',
      data: { id: 'task-1' },
    })
    await expect(deleteValidationAuditTask('task-1')).resolves.toEqual({
      success: true,
      message: '删除成功',
    })

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      'http://backend.test/api/v1/registration/validation-audit/tasks',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      'http://backend.test/api/v1/registration/validation-audit/tasks/task-1',
      expect.objectContaining({ method: 'DELETE' }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/registration/validation-audit')
  })
})
