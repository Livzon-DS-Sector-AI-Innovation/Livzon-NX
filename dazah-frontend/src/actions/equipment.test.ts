import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getServerToken: vi.fn().mockResolvedValue('server-token'),
  revalidatePath: vi.fn(),
}))

vi.mock('@/lib/auth', () => ({ getServerToken: mocks.getServerToken }))
vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidatePath }))

import { createCategory, createEquipment, deleteCategory, updateWorkOrder } from './equipment'

const API_BASE = 'http://localhost:8000'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('equipment actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('creates a category with auth header', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { id: 'c-1' } }))
    vi.stubGlobal('fetch', fetchMock)

    const payload = { name: '反应釜', parent_id: null }
    await createCategory(payload as never)
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/equipment/categories`,
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify(payload),
        headers: expect.objectContaining({ Authorization: 'Bearer server-token' }),
      }),
    )
  })

  it('creates an equipment record', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { id: 'eq-1' } }))
    vi.stubGlobal('fetch', fetchMock)

    const payload = { name: '发酵罐', category_id: 'c-1', equipment_no: 'EQ-001' }
    await createEquipment(payload as never)
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/equipment/equipments`,
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('deletes a category', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: null }))
    vi.stubGlobal('fetch', fetchMock)

    await deleteCategory('c-1')
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/equipment/categories/c-1`,
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

  it('updates a work order', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { id: 'wo-1' } }))
    vi.stubGlobal('fetch', fetchMock)

    const payload = { status: 'in_progress' }
    await updateWorkOrder('wo-1', payload as never)
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/equipment/maintenance/work-orders/wo-1`,
      expect.objectContaining({ method: 'PUT' }),
    )
  })

  it('surfaces backend error message', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ message: '设备编号重复' }, 400))
    vi.stubGlobal('fetch', fetchMock)

    await expect(createEquipment({ name: 'x' } as never)).rejects.toThrow('设备编号重复')
  })
})
