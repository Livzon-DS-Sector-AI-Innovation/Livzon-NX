import { afterEach, describe, expect, it, vi } from 'vitest'
import { QUALITY_LABELS, estimateUsage, formatAmount, ledgerRequest, reportQuery, resolveLedgerAction } from './energy-ledger'

afterEach(() => vi.unstubAllGlobals())

describe('energy entry precision and draft submissions', () => {
  it('labels reviewed exceptions as pending confirmation', () => { expect(QUALITY_LABELS.pending_review).toBe('待确认') })
  it('shows structured Server Action errors in production without relying on thrown server errors', async () => {
    await expect(resolveLedgerAction(Promise.resolve({ ok: false, message: '数据已被其他人修改，请刷新' }))).rejects.toThrow('数据已被其他人修改')
    expect(await resolveLedgerAction(Promise.resolve({ ok: true, data: 0 }))).toBe(0)
  })
  it('estimates counter differences exactly and preserves large values', () => {
    expect(estimateUsage('0.3', '0.1', '10', false)).toBe('2')
    expect(estimateUsage('9007199254740993.1', '9007199254740993', '1', false)).toBe('0.1')
    expect(estimateUsage('0', '0E-8', '1', false)).toBe('0')
    expect(estimateUsage('9', '10', '1', false)).toBeUndefined()
    expect(estimateUsage('12.5', null, '2', true)).toBe('25')
  })
  it('distinguishes missing from zero and keeps significant digits', () => {
    expect(formatAmount(null)).toBe('—')
    expect(formatAmount('0E-8')).toBe('0')
    expect(formatAmount('10.1000')).toBe('10.1')
    expect(formatAmount('100')).toBe('100')
  })
  it('serializes filters without dropping numeric zero', () => {
    expect(reportQuery({ start_date: '2026-07-01', workshop: '101车间', page: 0, category: undefined })).toBe('start_date=2026-07-01&workshop=101%E8%BD%A6%E9%97%B4&page=0')
  })
  it('returns useful authorization errors without swallowing them', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ message: '无权填写该原始数据' }), { status: 403 })))
    await expect(ledgerRequest('/input-readings')).rejects.toThrow('无权填写该原始数据')
  })
  it.each([500, 502])('handles plain-text server errors without leaking their content (%s)', async status => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('Internal Server Error', { status })))
    await expect(ledgerRequest('/reporting')).rejects.toThrow(`能源服务暂不可用（${status}），请稍后重试`)
  })
  it('handles malformed successful responses as an energy service error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>upstream page</html>', { status: 200 })))
    await expect(ledgerRequest('/reporting')).rejects.toThrow('能源服务返回格式异常，请稍后重试')
  })
})
