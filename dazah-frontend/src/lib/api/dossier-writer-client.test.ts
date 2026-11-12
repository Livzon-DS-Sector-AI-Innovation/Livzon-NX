import { afterEach, expect, it, vi } from 'vitest'
import {
  deleteProductDossier,
  fetchProductDossier,
  fetchProductDossiers,
  updateProductDossier,
} from './dossier-writer-client'

afterEach(() => vi.unstubAllGlobals())

it.each([
  () => fetchProductDossiers(),
  () => fetchProductDossier('dossier-1'),
  () => updateProductDossier('dossier-1', {}),
  () => deleteProductDossier('dossier-1'),
])('rejects a forbidden dossier request', async (request) => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 403 })))
  await expect(request()).rejects.toThrow('没有执行此操作的权限')
})

it('keeps a successful delete usable', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 200 }))
  vi.stubGlobal('fetch', fetchMock)
  await expect(deleteProductDossier('dossier-1')).resolves.toBeUndefined()
  expect(fetchMock).toHaveBeenCalledWith('/api/v1/dossier-writer/products/dossier-1', { method: 'DELETE' })
})
