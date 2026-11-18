import { afterEach, expect, it, vi } from 'vitest'
vi.mock('@/lib/auth', () => ({ getAuthHeaders: vi.fn().mockResolvedValue({
  Authorization: 'Bearer fixture', 'X-Dazah-Operation-ID': 'fixture-operation', 'Content-Type': 'application/json',
}) }))
vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))
import { uploadWorkOrderImages } from './equipment'
import { createRole } from './equipment-personnel'
import { revalidatePath } from 'next/cache'

afterEach(() => vi.unstubAllGlobals())

it('forwards operation IDs through equipment writes and lets uploads set their own multipart boundary', async () => {
  const fetcher = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ data: { id: 'fixture' } })))
  vi.stubGlobal('fetch', fetcher)
  const upload = new FormData()
  upload.append('files', new Blob(['fixture']), 'fixture.jpg')
  await expect(uploadWorkOrderImages('fixture-order', upload)).resolves.toMatchObject({ ok: true })
  for (const [, options] of fetcher.mock.calls) {
    expect(options.headers['X-Dazah-Operation-ID']).toBe('fixture-operation')
    expect(options.headers['Content-Type']).toBeUndefined()
    expect(options.body).toBe(upload)
  }
  await createRole({ name: 'fixture' } as never)
  for (const [, options] of fetcher.mock.calls.slice(1)) {
    expect(options.headers['X-Dazah-Operation-ID']).toBe('fixture-operation')
    expect(options.headers['Content-Type']).toBe('application/json')
  }
})

it.each([
  [413, null, '文件过大，请缩小文件后重试'],
  [415, null, '文件格式不受支持，请检查后重试'],
  [403, null, '没有执行此操作的权限，请联系管理员'],
  [400, 'EQUIPMENT_WORK_ORDER_IMAGE_LIMIT', '此工单最多保留 9 张图片，请减少本次上传的图片数量'],
  [400, 'UNKNOWN', '请求内容有误，请检查后重试'],
])('maps upload failures for HTTP %i', async (status, code, message) => {
  vi.mocked(revalidatePath).mockClear()
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
    message: '内部错误详情', detail: code ? { error_code: code } : null,
  }), { status })))
  const upload = new FormData()
  upload.append('files', new Blob(['fixture']), 'fixture.jpg')
  await expect(uploadWorkOrderImages('fixture-order', upload)).resolves.toEqual({ ok: false, message })
  expect(revalidatePath).not.toHaveBeenCalled()
})
