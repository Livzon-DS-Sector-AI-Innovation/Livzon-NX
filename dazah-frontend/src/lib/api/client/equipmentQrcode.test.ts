/* @vitest-environment happy-dom */
import { afterEach, expect, it, vi } from 'vitest'
import { fetchEquipmentQrcodePdf } from './equipmentQrcode'

afterEach(() => vi.unstubAllGlobals())

function stubObjectUrl() {
  const createObjectURL = vi.fn(() => 'blob:mock')
  const revokeObjectURL = vi.fn()
  vi.stubGlobal('URL', Object.assign(URL, { createObjectURL, revokeObjectURL }))
  return { createObjectURL, revokeObjectURL }
}

it('requests the workshop pdf and triggers a blob download', async () => {
  const blob = new Blob(['%PDF-fake'], { type: 'application/pdf' })
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    blob: async () => blob,
    headers: new Headers(),
  })
  vi.stubGlobal('fetch', fetchMock)
  const { createObjectURL, revokeObjectURL } = stubObjectUrl()

  await fetchEquipmentQrcodePdf('201-1')

  const [url] = fetchMock.mock.calls[0]
  expect(new URL(url, 'http://test').searchParams.get('workshop')).toBe('201-1')
  expect(new URL(url, 'http://test').pathname).toBe(
    '/api/v1/equipment/equipments/qrcode-pdf'
  )
  expect(createObjectURL).toHaveBeenCalledTimes(1)
  expect(createObjectURL.mock.calls[0][0]).toBeInstanceOf(Blob)
  expect(revokeObjectURL).toHaveBeenCalledWith('blob:mock')
})

it('prefers the server-provided UTF-8 filename', async () => {
  const encoded = encodeURIComponent('设备报修码_201-1.pdf')
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: true,
      blob: async () => new Blob(['%PDF-fake']),
      headers: new Headers({
        'content-disposition': `attachment; filename*=UTF-8''${encoded}`,
      }),
    })
  )
  const { createObjectURL } = stubObjectUrl()
  await fetchEquipmentQrcodePdf('201-1')
  expect(createObjectURL).toHaveBeenCalled()
})

it('surfaces a backend failure with status code', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok: false, status: 404, headers: new Headers() })
  )
  await expect(fetchEquipmentQrcodePdf('404-x')).rejects.toThrow(
    '设备码导出失败: 404'
  )
})

it('reports an abort as a friendly timeout message', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockRejectedValue(
      new DOMException('The operation was aborted.', 'AbortError')
    )
  )
  await expect(fetchEquipmentQrcodePdf('201-1')).rejects.toThrow(
    '导出超时（>30秒），请重试'
  )
})
