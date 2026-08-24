import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  actionFetch: vi.fn().mockResolvedValue({ id: 'deviation-1' }),
  revalidatePath: vi.fn(),
}))

vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidatePath }))
vi.mock('./quality-shared', () => ({
  API_BASE_URL: 'http://backend.test',
  actionFetch: mocks.actionFetch,
}))

import { deleteDeviation, submitDeviation } from './quality-deviation'

describe('quality deviation server actions', () => {
  afterEach(() => vi.clearAllMocks())

  it('keeps submit and delete operations on the migrated endpoints', async () => {
    await submitDeviation('deviation-1')
    await deleteDeviation('deviation-1')

    expect(mocks.actionFetch).toHaveBeenNthCalledWith(
      1,
      'http://backend.test/api/v1/quality/deviations/deviation-1/submit',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(mocks.actionFetch).toHaveBeenNthCalledWith(
      2,
      'http://backend.test/api/v1/quality/deviations/deviation-1',
      expect.objectContaining({ method: 'DELETE' }),
    )
  })
})
