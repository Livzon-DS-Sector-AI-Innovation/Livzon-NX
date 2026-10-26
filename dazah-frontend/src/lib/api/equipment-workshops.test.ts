import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  createEquipmentWorkshop,
  fetchAllEquipmentWorkshops,
  fetchEquipmentWorkshops,
  updateEquipmentWorkshop,
} from './equipment-workshops'

function jsonResponse(data: unknown, code = 200) {
  return new Response(JSON.stringify({ code, data }), { status: 200 })
}

describe('equipment workshops api', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('lists enabled workshops and the full registry', async () => {
    const fetchMock = vi.fn().mockImplementation(async () =>
      jsonResponse([{ code: '201-1', name: '201一车间', is_enabled: true }]),
    )
    vi.stubGlobal('fetch', fetchMock)

    const enabled = await fetchEquipmentWorkshops()
    const all = await fetchAllEquipmentWorkshops()

    expect(enabled).toHaveLength(1)
    expect(all).toHaveLength(1)
    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/v1/equipment/workshops')
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/v1/equipment/workshops/all',
    )
  })

  it('creates workshops and updates them by immutable code', async () => {
    const fetchMock = vi
      .fn()
      .mockImplementation(async () =>
        jsonResponse({ code: 'dlz', name: '动力站', is_enabled: true }),
      )
    vi.stubGlobal('fetch', fetchMock)

    await createEquipmentWorkshop({ code: 'dlz', name: '动力站' })
    await updateEquipmentWorkshop('dlz', { name: '动力一站', is_enabled: false })

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      '/api/v1/equipment/workshops',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/v1/equipment/workshops/dlz',
      expect.objectContaining({ method: 'PUT' }),
    )
  })
})
