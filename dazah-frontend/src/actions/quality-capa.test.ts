import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  actionFetch: vi.fn().mockResolvedValue({ ok: true }),
  revalidatePath: vi.fn(),
}))

vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidatePath }))
vi.mock('./quality-shared', () => ({
  API_BASE_URL: 'http://backend.test',
  actionFetch: mocks.actionFetch,
}))

import { addExecutionTrack, deleteExecutionTrack, submitEvaluation } from './quality-capa'

describe('quality CAPA server actions', () => {
  afterEach(() => vi.clearAllMocks())

  it('uses the migrated execution and evaluation endpoints', async () => {
    await addExecutionTrack('capa-1', { result: '完成' })
    await deleteExecutionTrack('capa-1', 2)
    await submitEvaluation('capa-1', { effective: true })

    expect(mocks.actionFetch).toHaveBeenNthCalledWith(
      1,
      'http://backend.test/api/v1/quality/capas/capa-1/add-execution-track',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(mocks.actionFetch).toHaveBeenNthCalledWith(
      2,
      'http://backend.test/api/v1/quality/capas/capa-1/delete-execution-track?index=2',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(mocks.actionFetch).toHaveBeenNthCalledWith(
      3,
      'http://backend.test/api/v1/quality/capas/capa-1/submit-evaluation',
      expect.objectContaining({ method: 'POST' }),
    )
  })
})
