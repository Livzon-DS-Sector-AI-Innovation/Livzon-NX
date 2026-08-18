import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getServerToken: vi.fn().mockResolvedValue('server-token'),
  revalidatePath: vi.fn(),
}))

vi.mock('@/lib/auth', () => ({ getServerToken: mocks.getServerToken }))
vi.mock('@/lib/server-api', () => ({
  getServerApiBaseUrl: () => 'http://backend.test',
}))
vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidatePath }))

import {
  deletePurchaseRequest,
  importPurchaseRequestTable,
  saveProcurementMaterialSource,
  syncProcurementMaterialSource,
  testProcurementMaterialSource,
} from './purchasing'

const payload = {
  source_url: 'https://feishu.cn/base/app-token?table=table-id',
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('procurement material source actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('tests and saves the material source through authenticated backend calls', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({ code: 200, message: 'success', data: { status: 'success' } }),
      )
      .mockResolvedValueOnce(
        jsonResponse({ code: 200, message: 'success', data: { id: 'config-1' } }),
      )
    vi.stubGlobal('fetch', fetchMock)

    await expect(testProcurementMaterialSource(payload)).resolves.toMatchObject({ code: 200 })
    await expect(saveProcurementMaterialSource(payload)).resolves.toMatchObject({ code: 200 })

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      'http://backend.test/api/v1/procurement/material-source-config/test',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify(payload),
        headers: expect.objectContaining({ Authorization: 'Bearer server-token' }),
      }),
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      'http://backend.test/api/v1/procurement/material-source-config',
      expect.objectContaining({ method: 'PUT', body: JSON.stringify(payload) }),
    )
    expect(mocks.revalidatePath.mock.calls).toEqual([
      ['/purchasing'],
      ['/purchasing/settings'],
    ])
  })

  it('imports a purchase request table with an auth header and revalidates', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        code: 200,
        message: 'success',
        data: { file_name: '申请.xlsx', total_sheets: 1, imported_requests: [], failed_rows: [] },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const formData = new FormData()
    formData.append('file', new File(['bytes'], '申请.xlsx'))
    await expect(importPurchaseRequestTable(formData)).resolves.toMatchObject({ code: 200 })

    expect(fetchMock).toHaveBeenCalledWith(
      'http://backend.test/api/v1/procurement/purchase-requests/import',
      expect.objectContaining({
        method: 'POST',
        body: formData,
        headers: expect.objectContaining({ Authorization: 'Bearer server-token' }),
      }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/purchasing')
  })

  it('imports without an auth header when no server token exists', async () => {
    mocks.getServerToken.mockResolvedValueOnce(null)
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ code: 200, message: 'success', data: null }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(importPurchaseRequestTable(new FormData())).resolves.toMatchObject({ code: 200 })

    const headers = fetchMock.mock.calls[0][1].headers as HeadersInit
    expect(headers).not.toHaveProperty('Authorization')
  })

  it('deletes a request and syncs the material source with revalidation', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({ code: 200, message: 'success', data: { success_count: 1, fail_count: 0 } }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          code: 200,
          message: 'success',
          data: { synced_count: 12, deactivated_count: 0 },
        }),
      )
    vi.stubGlobal('fetch', fetchMock)

    await expect(deletePurchaseRequest('req-1')).resolves.toMatchObject({ code: 200 })
    await expect(syncProcurementMaterialSource()).resolves.toMatchObject({ code: 200 })

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      'http://backend.test/api/v1/procurement/purchase-requests/req-1',
      expect.objectContaining({ method: 'DELETE' }),
    )
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      'http://backend.test/api/v1/procurement/material-source-config/sync',
      expect.objectContaining({ method: 'POST', body: JSON.stringify({}) }),
    )
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/purchasing')
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/purchasing/material-library')
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/purchasing/settings')
  })
})
