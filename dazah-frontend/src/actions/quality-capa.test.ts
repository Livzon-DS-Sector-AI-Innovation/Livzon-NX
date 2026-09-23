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

import { addExecutionTrack, deleteExecutionTrack, submitEvaluation, updateCapa } from './quality-capa'

describe('quality CAPA server actions', () => {
  afterEach(() => vi.clearAllMocks())

  it('returns the backend sync result without starting a second Feishu write', async () => {
    const saved = { success: true, feishu_sync_status: 'failed' }
    mocks.actionFetch.mockResolvedValueOnce(saved)
    expect(await updateCapa('capa-1', { capa_content: '更新措施' })).toEqual(saved)
    expect(mocks.actionFetch).toHaveBeenCalledTimes(1)
    expect(mocks.actionFetch).toHaveBeenCalledWith(
      'http://backend.test/api/v1/quality/capas/capa-1',
      { method: 'PUT', body: JSON.stringify({ capa_content: '更新措施' }) },
    )
  })

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
