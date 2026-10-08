import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { isMaintenanceActive, protectFetch, readMaintenance } from './maintenance-client'

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })
beforeEach(() => vi.stubGlobal('window', { location: { href: 'http://fixture/quality', origin: 'http://fixture' } }))

describe('release maintenance request gate', () => {
  it('allows retries after read failures without receipts or operation IDs', async () => {
    const original = vi.fn<typeof fetch>().mockRejectedValueOnce(new Error('read failed')).mockResolvedValue(new Response('{}'))
    const controller = new AbortController()
    const request = protectFetch(original, () => ({ phase: 'normal' }), () => controller.signal)
    const init = { method: 'POST', headers: { 'Next-Action': 'read-fixture' }, body: '[]' }
    await expect(request('/quality', init)).rejects.toThrow('read failed')
    await request('/quality', init)
    expect(original).toHaveBeenCalledTimes(2)
    for (const [input] of original.mock.calls) expect((input as Request).headers.has('X-Dazah-Operation-ID')).toBe(false)
  })

  it.each(['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])('blocks all same-origin requests during maintenance: %s', async method => {
    const original = vi.fn()
    const request = protectFetch(original, () => ({ phase: 'maintenance' }), () => new AbortController().signal)
    for (const path of ['/api/v1/quality', '/settings', '/api/v1/system/operations/fixture']) {
      await expect(request(path, { method })).rejects.toThrow('请停止操作')
    }
    expect(original).not.toHaveBeenCalled()
  })

  it('keeps the status probe available and leaves external requests untouched', async () => {
    const original = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    const request = protectFetch(original, () => ({ phase: 'maintenance' }), () => new AbortController().signal)
    await request('/__dazah_maintenance_status')
    await request('https://external.test/resource')
    expect(original.mock.calls.map(call => call[0])).toEqual(['/__dazah_maintenance_status', 'https://external.test/resource'])
  })

  it('cancels admitted requests at release start and uses a fresh signal after recovery', async () => {
    let controller = new AbortController()
    const signals: AbortSignal[] = []
    const original = vi.fn<typeof fetch>().mockImplementation(input => {
      const signal = (input as Request).signal
      signals.push(signal)
      return new Promise((_, reject) => signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError'))))
    })
    const request = protectFetch(original, () => ({ phase: 'normal' }), () => controller.signal)
    const pending = request('/api/v1/quality')
    const rejected = expect(pending).rejects.toMatchObject({ name: 'AbortError' })
    controller.abort()
    await rejected
    expect(signals[0].aborted).toBe(true)
    controller = new AbortController()
    original.mockResolvedValueOnce(new Response('recovered'))
    expect(await (await request('/api/v1/quality')).text()).toBe('recovered')
    expect((original.mock.calls[1][0] as Request).signal.aborted).toBe(false)
  })

  it('preserves caller cancellation', async () => {
    const original = vi.fn().mockResolvedValue(new Response('ok'))
    const caller = new AbortController()
    const request = protectFetch(original, () => ({ phase: 'normal' }), () => new AbortController().signal)
    await request('/api/v1/quality', { signal: caller.signal })
    caller.abort()
    expect(original.mock.calls[0][0].signal.aborted).toBe(true)
  })

  it('permits saving during three-minute notice, then closes before the next probe', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(1_000_000)
    const state = { phase: 'announced' as const, starts_at: 1180 }
    const original = vi.fn().mockResolvedValue(new Response('ok'))
    const request = protectFetch(original, () => state, () => new AbortController().signal)
    expect(isMaintenanceActive(state)).toBe(false)
    await request('/settings', { method: 'POST' })
    vi.setSystemTime(1_180_000)
    await expect(request('/settings', { method: 'POST' })).rejects.toThrow('请停止操作')
    expect(original).toHaveBeenCalledOnce()
  })

  it('recognizes explicit maintenance, expiry and recovery without treating outages as recovery', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ phase: 'announced', starts_at: Date.now() / 1000 + 180 })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ phase: 'announced', starts_at: 1 })))
      .mockResolvedValueOnce(new Response('', { status: 503, headers: { 'X-Dazah-Maintenance': '1' } }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(new Response('', { status: 503 }))
    expect((await readMaintenance(fetcher))?.phase).toBe('announced')
    expect(await readMaintenance(fetcher)).toEqual({ phase: 'maintenance' })
    expect(await readMaintenance(fetcher)).toEqual({ phase: 'maintenance' })
    expect(await readMaintenance(fetcher)).toEqual({ phase: 'normal' })
    expect(await readMaintenance(fetcher)).toBeNull()
  })
})
