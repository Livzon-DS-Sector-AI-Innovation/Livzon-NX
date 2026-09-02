import { afterEach, expect, it, vi } from 'vitest'
import { fetchDeviationReporters } from './deviation-reporters'

afterEach(() => vi.unstubAllGlobals())

it('sends bounded searches and forwards cancellation', async () => {
  const data = { data: [{ open_id: 'id', name: '报告人', department: '质量部' }], meta: { total: 1 } }
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => data })
  vi.stubGlobal('fetch', fetch)
  const controller = new AbortController()
  expect(await fetchDeviationReporters(' 王 ', controller.signal)).toEqual(data)
  const [url, options] = fetch.mock.calls[0]
  expect(new URL(url, 'http://test').searchParams.get('keyword')).toBe('王')
  expect(new URL(url, 'http://test').searchParams.get('page_size')).toBe('50')
  expect(options.signal).toBe(controller.signal)
})

it('preserves a Chinese permission or upstream error', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, json: async () => ({ detail: '报告人目录响应超时，请稍后重试' }) }))
  await expect(fetchDeviationReporters('')).rejects.toThrow('报告人目录响应超时')
})
