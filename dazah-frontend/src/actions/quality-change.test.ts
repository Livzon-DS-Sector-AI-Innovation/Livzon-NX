import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  actionFetch: vi.fn().mockResolvedValue({ id: 'change-1' }),
  revalidatePath: vi.fn(),
}))

vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidatePath }))
vi.mock('./quality-shared', async (importOriginal) => ({
  ...await importOriginal<typeof import('./quality-shared')>(),
  API_BASE_URL: 'http://backend.test',
  actionFetch: mocks.actionFetch,
}))

import { confirmChangeImport, createChange, deleteChange, previewChangeImport } from './quality-change'
import { qualityImportErrorMessages } from './quality-shared'

describe('quality change server actions', () => {
  afterEach(() => vi.clearAllMocks())

  it('uses the Word import error contract for preview and confirmation', async () => {
    const form = new FormData()
    await previewChangeImport(form)
    await confirmChangeImport(form, true, false)

    expect(mocks.actionFetch).toHaveBeenNthCalledWith(
      1, 'http://backend.test/api/v1/quality/changes/import/preview?change_type=technical',
      { method: 'POST', body: form }, qualityImportErrorMessages,
    )
    expect(mocks.actionFetch).toHaveBeenNthCalledWith(
      2, 'http://backend.test/api/v1/quality/changes/import/confirm?skip_duplicates=true&update_existing=false&change_type=technical',
      { method: 'POST', body: form }, qualityImportErrorMessages,
    )
  })

  it('routes create and delete operations through the quality API', async () => {
    await createChange({ title: '变更评估' } as never)
    await deleteChange('change-1')

    expect(mocks.actionFetch).toHaveBeenNthCalledWith(
      1,
      'http://backend.test/api/v1/quality/changes',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(mocks.actionFetch).toHaveBeenNthCalledWith(
      2,
      'http://backend.test/api/v1/quality/changes/change-1',
      expect.objectContaining({ method: 'DELETE' }),
    )
  })
})
