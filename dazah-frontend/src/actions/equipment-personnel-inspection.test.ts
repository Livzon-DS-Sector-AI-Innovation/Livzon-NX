import { afterEach, expect, it, vi } from 'vitest'
vi.mock('@/lib/auth', () => ({ getAuthHeaders: vi.fn().mockResolvedValue({
  Authorization: 'Bearer fixture', 'X-Dazah-Operation-ID': 'fixture-operation', 'Content-Type': 'application/json',
}) }))
vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))
import { uploadWorkOrderImages } from './equipment'
import { createRole } from './equipment-personnel'
import { uploadTaskPhoto, submitRouteCheck } from './inspection'

afterEach(() => vi.unstubAllGlobals())

it('forwards operation IDs through equipment writes and lets uploads set their own multipart boundary', async () => {
  const fetcher = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ data: { id: 'fixture' } })))
  vi.stubGlobal('fetch', fetcher)
  const upload = new FormData()
  upload.append('file', new Blob(['fixture']), 'fixture.txt')
  await uploadWorkOrderImages('fixture-order', upload)
  await uploadTaskPhoto('fixture-task', upload)
  for (const [, options] of fetcher.mock.calls) {
    expect(options.headers['X-Dazah-Operation-ID']).toBe('fixture-operation')
    expect(options.headers['Content-Type']).toBeUndefined()
    expect(options.body).toBe(upload)
  }
  await createRole({ name: 'fixture' } as never)
  await submitRouteCheck('fixture', {} as never)
  for (const [, options] of fetcher.mock.calls.slice(2)) {
    expect(options.headers['X-Dazah-Operation-ID']).toBe('fixture-operation')
    expect(options.headers['Content-Type']).toBe('application/json')
  }
})
