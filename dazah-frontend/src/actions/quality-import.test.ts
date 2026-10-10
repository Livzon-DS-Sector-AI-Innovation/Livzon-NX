import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))
vi.mock('@/lib/auth', () => ({ getAuthHeaders: async () => ({ 'X-Dazah-Page-Path': '/quality/change' }) }))

import * as imports from './quality-import'
const { confirmChangeImport, previewChangeImport } = imports

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

describe('quality import safe server boundary', () => {
  it('preserves import options, permission context and successful response', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: { success_count: 1, error_count: 0 } })))
    vi.stubGlobal('fetch', fetch)
    const file = new FormData()
    expect(await confirmChangeImport(file, true, true, 'file')).toMatchObject({ ok: true, data: { success_count: 1 } })
    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('change_type=file'), expect.objectContaining({
      method: 'POST', body: file, headers: { 'X-Dazah-Page-Path': '/quality/change' },
    }))
  })
  it.each(Object.keys(imports) as (keyof typeof imports)[])('returns authorization rejection as data: %s', async (name) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: '未获得当前高风险业务动作授权' }), { status: 403 })))
    const action = imports[name]
    const result = name.includes('Legacy')
      ? await (action as typeof imports.confirmLegacyChangeImport)(new FormData(), { skipDuplicates: true, updateExisting: false })
      : await (action as typeof imports.confirmChangeImport)(new FormData(), true, false)
    expect(result).toEqual({ ok: false, message: '未获得当前高风险业务动作授权' })
  })
  it('hides an upstream 500 and malformed responses, without rejecting the action', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const fetch = vi.fn().mockResolvedValueOnce(new Response('private SQL', { status: 500 }))
      .mockResolvedValueOnce(new Response('not JSON'))
    vi.stubGlobal('fetch', fetch)
    expect(await confirmChangeImport(new FormData(), true, false)).toMatchObject({ ok: false })
    expect(await previewChangeImport(new FormData())).toMatchObject({ ok: false })
  })
})
