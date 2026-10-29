import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ auth: vi.fn(), fetch: vi.fn(), revalidate: vi.fn() }))
vi.mock('@/lib/auth', () => ({ getAuthHeaders: mocks.auth }))
vi.mock('@/lib/server-api', () => ({ getServerApiBaseUrl: () => 'http://backend.test:8000' }))
vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidate }))

import { parseExperimentRecord, parseProcessParameters } from './ai-parse'

beforeEach(() => {
  vi.resetAllMocks()
  mocks.auth.mockResolvedValue({ Authorization: 'Bearer synthetic', 'Content-Type': 'application/json' })
  vi.stubGlobal('fetch', mocks.fetch)
})
afterEach(() => vi.unstubAllGlobals())

describe('AI parsing authentication and safe errors', () => {
  const actions = [
    { name: 'file', run: () => parseExperimentRecord(new File(['record'], 'record.txt'), 'scale_up') },
    { name: 'parameters', run: () => parseProcessParameters('温度 25℃', 'lab_confirmation') },
  ]

  it.each(actions)('rejects $name parsing without authentication before sending data', async ({ run }) => {
    mocks.auth.mockResolvedValue({ 'Content-Type': 'application/json' })
    await expect(run()).rejects.toThrow('未登录或登录已过期')
    expect(mocks.fetch).not.toHaveBeenCalled()
    expect(mocks.revalidate).not.toHaveBeenCalled()
  })

  it.each(actions)('hides upstream error bodies for $name parsing', async ({ run }) => {
    const response = new Response('synthetic-secret: internal upstream diagnostics', { status: 502 })
    const readBody = vi.spyOn(response, 'text')
    mocks.fetch.mockResolvedValue(response)
    await expect(run()).rejects.toThrow(/^解析失败（502）$/)
    expect(readBody).not.toHaveBeenCalled()
    expect(mocks.revalidate).not.toHaveBeenCalled()
  })

  it('forwards the file and parse type with bearer auth and lets fetch set the multipart boundary', async () => {
    const file = new File(['record'], 'record.txt', { type: 'text/plain' })
    const data = { parameters: [{ name: '温度', value: 25 }] }
    mocks.fetch.mockResolvedValue(new Response(JSON.stringify({ data })))
    await expect(parseExperimentRecord(file, 'scale_up')).resolves.toEqual(data)
    const [url, init] = mocks.fetch.mock.calls[0]
    expect(url).toBe('http://backend.test:8000/api/v1/ai/parse-experiment')
    expect(init).toEqual(expect.objectContaining({ method: 'POST', headers: { Authorization: 'Bearer synthetic' } }))
    expect(init.body).toBeInstanceOf(FormData)
    expect(init.body.get('file').name).toBe('record.txt')
    expect(await init.body.get('file').text()).toBe('record')
    expect(init.body.get('parse_type')).toBe('scale_up')
    expect(mocks.revalidate).toHaveBeenCalledExactlyOnceWith('/rd/process-optimization')
  })

  it('forwards JSON parameters with authentication and returns parsed data', async () => {
    const data = { temperature: 25 }
    mocks.fetch.mockResolvedValue(new Response(JSON.stringify({ data })))
    await expect(parseProcessParameters('温度 25℃', 'lab_confirmation')).resolves.toEqual(data)
    expect(mocks.fetch).toHaveBeenCalledExactlyOnceWith('http://backend.test:8000/api/v1/ai/parse-parameters', {
      method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer synthetic' },
      body: JSON.stringify({ content: '温度 25℃', parse_type: 'lab_confirmation' }),
    })
    expect(mocks.revalidate).not.toHaveBeenCalled()
  })
})
