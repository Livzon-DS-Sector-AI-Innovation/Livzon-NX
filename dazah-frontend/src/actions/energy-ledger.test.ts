import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))
vi.mock('@/lib/auth', () => ({ getAuthHeaders: async () => ({ 'Content-Type': 'application/json' }) }))
vi.mock('@/lib/api/energy-ledger', async importOriginal => ({
  ...await importOriginal<typeof import('@/lib/api/energy-ledger')>(),
  ledgerRequest: vi.fn(),
}))

import { ledgerRequest } from '@/lib/api/energy-ledger'
import { previewLedgerImport } from './energy-ledger'

afterEach(() => vi.clearAllMocks())

describe('energy import server action', () => {
  it('sends the selected date boundaries as query parameters and preserves the file', async () => {
    vi.mocked(ledgerRequest).mockResolvedValue({ id: 'batch', status: 'preview', payload: {} })
    const data = new FormData()
    data.set('year', '2026'); data.set('start_date', '2026-06-27'); data.set('end_date', '2026-07-19')
    data.set('file', new Blob(['workbook']), 'energy.xlsx')
    expect((await previewLedgerImport(data)).ok).toBe(true)
    expect(ledgerRequest).toHaveBeenCalledWith('/imports/preview?year=2026&start_date=2026-06-27&end_date=2026-07-19', { method: 'POST', body: data }, {})
    expect(data.get('file')).toBeInstanceOf(Blob)
    expect(data.has('start_date')).toBe(false)
  })
  it('returns a structured failure without losing the selected date boundaries', async () => {
    vi.mocked(ledgerRequest).mockRejectedValue(new Error('offline'))
    const data = new FormData(); data.set('year', '2026'); data.set('end_date', '2026-07-19')
    expect((await previewLedgerImport(data)).ok).toBe(false)
    expect(ledgerRequest).toHaveBeenCalledWith('/imports/preview?year=2026&end_date=2026-07-19', expect.anything(), {})
  })
})
