import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { webcrypto } from 'node:crypto'
import { protectFetch, readMaintenance } from './maintenance-client'
import type { ProtectedOperation } from './maintenance-client'

afterEach(() => vi.unstubAllGlobals())
beforeEach(() => vi.stubGlobal('window', { location: { href: 'http://fixture/quality', origin: 'http://fixture' } }))

describe('maintenance input and submission protection', () => {
  it('coalesces simultaneous identical Actions without repeating a write or consuming either reply', async () => {
    vi.stubGlobal('crypto', webcrypto)
    let finish: (response: Response) => void = () => {}
    const original = vi.fn<typeof fetch>().mockImplementation(input => input instanceof Request ?
      new Promise(resolve => { finish = resolve }) : Promise.resolve(new Response('{}', { status: 404 })))
    const operations = new Map<string, ProtectedOperation>()
    const request = protectFetch(original, () => ({ phase: 'normal' }), operations, vi.fn())
    const init = { method: 'POST', headers: { 'Next-Action': 'fixture-write' }, body: '[]' }
    const first = request('/quality', init)
    await vi.waitFor(() => expect(original).toHaveBeenCalledOnce())
    const second = request('/quality', init)
    await new Promise(resolve => setTimeout(resolve, 20))
    finish(new Response('one business result'))
    const replies = await Promise.all([first, second])
    expect(await Promise.all(replies.map(reply => reply.text()))).toEqual(['one business result', 'one business result'])
    expect(original.mock.calls.filter(call => call[0] instanceof Request)).toHaveLength(1)
    expect(operations.size).toBe(1)
  })
  it('allows repeated read-only Server Actions after confirmed backend reads', async () => {
    vi.stubGlobal('crypto', webcrypto)
    let id = ''
    const original = vi.fn<typeof fetch>().mockImplementation(async input => {
      if (input instanceof Request) {
        id = input.headers.get('X-Dazah-Operation-ID') || ''
        return new Response('fixture flight result')
      }
      return new Response(JSON.stringify({ operation_id: id, receipts: [{ method: 'GET', state: 'completed' }] }))
    })
    const operations = new Map<string, ProtectedOperation>()
    const request = protectFetch(original, () => ({ phase: 'normal' }), operations, vi.fn())
    const init = { method: 'POST', headers: { 'Next-Action': 'fixture-read' }, body: '[]' }
    await request('/quality', init)
    await vi.waitFor(() => expect(operations.size).toBe(0))
    await request('/quality', init)
    await vi.waitFor(() => expect(operations.size).toBe(0))
    expect(original.mock.calls.filter(call => call[0] instanceof Request)).toHaveLength(2)
  })

  it('keeps completed writes guarded until reconciliation, even when the Action reply is HTTP 200', async () => {
    vi.stubGlobal('crypto', webcrypto)
    let id = ''
    const original = vi.fn<typeof fetch>().mockImplementation(async input => {
      if (input instanceof Request) {
        id = input.headers.get('X-Dazah-Operation-ID') || ''
        return new Response('fixture partial action result')
      }
      return new Response(JSON.stringify({ operation_id: id, receipts: [{ method: 'POST', state: 'completed' }] }))
    })
    const operations = new Map<string, ProtectedOperation>()
    const request = protectFetch(original, () => ({ phase: 'normal' }), operations, vi.fn())
    const init = { method: 'POST', headers: { 'Next-Action': 'fixture-write' }, body: '[]' }
    await request('/quality', init)
    await vi.waitFor(() => expect(original).toHaveBeenCalledTimes(2))
    await expect(request('/quality', init)).rejects.toThrow('先查询操作结果')
    expect(original.mock.calls.filter(call => call[0] instanceof Request)).toHaveLength(1)
    expect([...operations.values()][0].id).toBe(id)
  })
  it('rechecks maintenance after asynchronously fingerprinting a submission', async () => {
    let phase: 'normal' | 'maintenance' = 'normal'
    vi.stubGlobal('crypto', { subtle: { digest: async () => { phase = 'maintenance'; return new ArrayBuffer(32) } } })
    const original = vi.fn()
    const operations = new Map<string, ProtectedOperation>()
    const request = protectFetch(original, () => ({ phase }), operations, vi.fn())
    await expect(request('/api/v1/quality/fixture', { method: 'POST', body: '{}' })).rejects.toThrow('本次操作未发送')
    expect(original).not.toHaveBeenCalled()
    expect(operations.size).toBe(0)
  })
  it('protects submissions on LAN HTTP without secure-context-only crypto APIs', async () => {
    vi.stubGlobal('crypto', { getRandomValues: webcrypto.getRandomValues.bind(webcrypto) })
    const original = vi.fn().mockRejectedValue(new Error('fixture lost response'))
    const operations = new Map<string, ProtectedOperation>()
    const request = protectFetch(original, () => ({ phase: 'normal' }), operations, vi.fn())
    const init = { method: 'POST', body: '{}' }
    await expect(request('/api/v1/quality/fixture', init)).rejects.toThrow('lost response')
    expect([...operations.values()][0].id).toMatch(/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/)
    await expect(request('/api/v1/quality/fixture', init)).rejects.toThrow('先查询操作结果')
    expect(original.mock.calls.filter(call => call[0] instanceof Request)).toHaveLength(1)
  })

  it('never blindly retries writes with opaque Request bodies', async () => {
    vi.stubGlobal('crypto', webcrypto)
    const original = vi.fn().mockRejectedValue(new Error('fixture lost response'))
    const request = protectFetch(original, () => ({ phase: 'normal' }), new Map(), vi.fn())
    await expect(request(new Request('http://fixture/api/v1/quality/import', { method: 'POST', body: new Blob(['fixture']) }))).rejects.toThrow('lost response')
    await expect(request(new Request('http://fixture/api/v1/quality/import', { method: 'POST', body: new Blob(['fixture']) }))).rejects.toThrow('先查询操作结果')
    expect(original.mock.calls.filter(call => call[0] instanceof Request)).toHaveLength(1)
  })
  it('reads a planned countdown, confirmed maintenance and normal recovery', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ phase: 'announced', starts_at: 2000 })))
      .mockResolvedValueOnce(new Response('', { status: 503, headers: { 'X-Dazah-Maintenance': '1' } }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(new Response('', { status: 503 }))
    expect(await readMaintenance(fetcher)).toEqual({ phase: 'announced', starts_at: 2000 })
    expect(await readMaintenance(fetcher)).toEqual({ phase: 'maintenance' })
    expect(await readMaintenance(fetcher)).toEqual({ phase: 'normal' })
    expect(await readMaintenance(fetcher)).toBeNull()
  })

  it('keeps a stable operation ID after a lost response and blocks a blind retry', async () => {
    vi.stubGlobal('crypto', webcrypto)
    const original = vi.fn().mockRejectedValue(new Error('fixture response lost'))
    const operations = new Map<string, ProtectedOperation>()
    const request = protectFetch(original, () => ({ phase: 'normal' }), operations, vi.fn())
    const init = { method: 'POST', headers: { 'Next-Action': 'fixture-action' }, body: '{"critical":"fixture"}' }
    await expect(request('/quality', init)).rejects.toThrow('fixture response lost')
    expect(operations.size).toBe(1)
    const id = [...operations.values()][0].id
    expect(original.mock.calls[0][0].headers.get('X-Dazah-Operation-ID')).toBe(id)
    await expect(request('/quality', init)).rejects.toThrow('先查询操作结果')
    expect(original.mock.calls.filter(call => call[0] instanceof Request)).toHaveLength(1)
    expect(JSON.stringify([...operations])).not.toContain('critical')
    operations.clear() // Explicit user reconciliation, never an automatic retry.
    original.mockResolvedValueOnce(new Response('fixture acknowledged'))
    await request('/quality', init)
    expect(original.mock.calls.filter(call => call[0] instanceof Request)[1][0].headers.get('X-Dazah-Operation-ID')).not.toBe(id)
  })

  it('blocks new business requests without cancelling already admitted requests', async () => {
    vi.stubGlobal('crypto', webcrypto)
    let phase: 'normal' | 'maintenance' = 'normal'
    let finish: (response: Response) => void = () => {}
    const original = vi.fn().mockImplementation(() => new Promise<Response>(resolve => { finish = resolve }))
    const request = protectFetch(original, () => ({ phase }), new Map(), vi.fn())
    const admitted = request('/api/v1/quality/fixture', { method: 'POST', body: '{}' })
    await vi.waitFor(() => expect(original).toHaveBeenCalledOnce())
    phase = 'maintenance'
    await expect(request('/api/v1/quality/fixture')).rejects.toThrow('本次操作未发送')
    expect(original).toHaveBeenCalledOnce()
    finish(new Response('completed'))
    expect((await admitted).ok).toBe(true)
  })

  it('allows saving during advance notice and never modifies third-party requests', async () => {
    vi.stubGlobal('crypto', webcrypto)
    const original = vi.fn().mockResolvedValue(new Response('ok'))
    const request = protectFetch(original, () => ({ phase: 'announced', starts_at: 1234 }), new Map(), vi.fn())
    await request('/api/v1/quality/fixture', { method: 'POST', body: '{}' })
    expect(original.mock.calls[0][0].headers.has('X-Dazah-Operation-ID')).toBe(true)
    await request('https://outside.invalid/fixture', { method: 'POST', body: '{}' })
    expect(original.mock.calls[1][0]).toBe('https://outside.invalid/fixture')
  })
})
