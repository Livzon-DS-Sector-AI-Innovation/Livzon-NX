import { afterEach, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ fetch: vi.fn(), revalidate: vi.fn() }))
vi.mock('./quality-shared', () => ({ API_BASE_URL: 'http://backend.test', actionFetch: mocks.fetch }))
vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidate }))
import { batchDeleteDeviations, createDeviation, deleteDeviation, submitDeviation } from './quality-deviation'

afterEach(() => vi.resetAllMocks())

it('keeps submit and delete operations on the migrated endpoints', async () => {
  mocks.fetch.mockResolvedValue({ id: 'deviation-1' })
  await submitDeviation('deviation-1')
  await deleteDeviation('deviation-1')
  expect(mocks.fetch).toHaveBeenNthCalledWith(
    1,
    'http://backend.test/api/v1/quality/deviations/deviation-1/submit',
    expect.objectContaining({ method: 'POST' }),
  )
  expect(mocks.fetch).toHaveBeenNthCalledWith(
    2,
    'http://backend.test/api/v1/quality/deviations/deviation-1',
    expect.objectContaining({ method: 'DELETE' }),
  )
})

it('forwards the selected reporter and returns the create contract', async () => {
  const result = { id: 'record-id', code: 'PC-CREATED' }
  mocks.fetch.mockResolvedValue(result)
  const body = { reporter_open_id: 'reporter-id', department: '质量部', description: '偏差', affected_items: '产品' }
  expect(await createDeviation(body)).toEqual(result)
  expect(mocks.fetch).toHaveBeenCalledWith('http://backend.test/api/v1/quality/deviations', { method: 'POST', body: JSON.stringify(body) })
  expect(mocks.revalidate).toHaveBeenCalled()
})

it('returns the atomic batch result without splitting the request', async () => {
  const result = { deleted: 2, failed: [] }
  mocks.fetch.mockResolvedValue(result)
  expect(await batchDeleteDeviations(['one', 'two'])).toEqual(result)
  expect(mocks.fetch).toHaveBeenCalledOnce()
  expect(mocks.fetch).toHaveBeenCalledWith('http://backend.test/api/v1/quality/deviations/batch-delete', { method: 'POST', body: JSON.stringify({ ids: ['one', 'two'] }) })
})

it('does not report success or refresh caches after a rejected batch', async () => {
  mocks.fetch.mockRejectedValue(new Error('偏差记录不在当前页面授权的部门范围内'))
  await expect(batchDeleteDeviations(['one', 'outside'])).rejects.toThrow('授权的部门范围')
  expect(mocks.revalidate).not.toHaveBeenCalled()
})
