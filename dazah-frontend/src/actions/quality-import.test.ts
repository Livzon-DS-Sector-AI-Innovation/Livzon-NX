import { afterEach, expect, it, vi } from 'vitest'
import { revalidatePath } from 'next/cache'
import * as actions from './quality-import'

vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))
vi.mock('@/lib/auth', () => ({ getAuthHeaders: async () => ({ Authorization: 'Bearer fixture' }) }))

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  vi.clearAllMocks()
})

const imports = [
  ['changes', actions.previewChangeImport, actions.previewLegacyChangeImport,
    actions.confirmChangeImport, actions.confirmLegacyChangeImport],
  ['capas', actions.previewCapaImport, actions.previewLegacyCapaImport,
    actions.confirmCapaImport, actions.confirmLegacyCapaImport],
  ['deviations', actions.previewDeviationImport, actions.previewLegacyDeviationImport,
    actions.confirmDeviationImport, actions.confirmLegacyDeviationImport],
] as const

it.each(imports)('uses the same error contract for both %s drawers', async (path, preview, legacyPreview, confirm, legacyConfirm) => {
  const file = new FormData()
  file.set('file', new Blob(['test']), 'test.docx')
  const options = { skipDuplicates: false, updateExisting: true }
  const fetcher = vi.fn()
  vi.stubGlobal('fetch', fetcher)

  for (const [index, call] of [
    () => preview(file), () => legacyPreview(file),
    () => confirm(file, false, true), () => legacyConfirm(file, options),
  ].entries()) {
    fetcher.mockResolvedValueOnce(new Response(JSON.stringify({
      message: '解析器内部信息', detail: { error_code: 'QUALITY_IMPORT_INVALID_DOCUMENT' },
    }), { status: 422 }))
    await expect(call()).resolves.toEqual({
      ok: false, message: '无法解析 Word 文档，请使用有效的 .docx 模板重新上传',
    })
    const [url, request] = fetcher.mock.calls[index]
    expect(new URL(url).pathname).toBe(`/api/v1/quality/${path}/import/${index < 2 ? 'preview' : 'confirm'}`)
    expect(request.body).toBe(file)
    if (index >= 2) {
      expect(new URL(url).searchParams.get('skip_duplicates')).toBe('false')
      expect(new URL(url).searchParams.get('update_existing')).toBe('true')
    }
  }
  expect(revalidatePath).not.toHaveBeenCalled()
})

it.each([
  [401, {}, '登录已失效，请重新登录'],
  [403, {}, '没有执行此操作的权限，请联系管理员'],
  [413, {}, '文件过大，请缩小文件后重试'],
  [415, { error_code: 'QUALITY_IMPORT_INVALID_DOCUMENT' }, '文件格式不受支持，请检查后重试'],
  [422, { error_code: 'UNRECOGNIZED' }, '填写内容有误，请检查后重试'],
])('falls back to the HTTP %i prompt without using the response text', async (status, detail, message) => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
    message: '无法解析 Word 文档，请使用有效的 .docx 模板重新上传', detail,
  }), { status })))
  await expect(actions.previewDeviationImport(new FormData())).resolves.toEqual({ ok: false, message })
})

it('preserves row-level partial success and refreshes after a confirmed result', async () => {
  const result = { success_count: 2, skipped_count: 1, error_count: 1, error_details: [{ row: 3, error: '编号不能为空' }] }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ data: result }))))
  await expect(actions.confirmCapaImport(new FormData(), true, false))
    .resolves.toEqual({ ok: true, data: result })
  expect(revalidatePath).toHaveBeenCalledWith('/quality/capas')
})

it('reports unknown write status with a reference and sends the write only once', async () => {
  vi.spyOn(console, 'error').mockImplementation(() => {})
  const fetcher = vi.fn().mockRejectedValue(new Error('内部网络信息'))
  vi.stubGlobal('fetch', fetcher)
  await expect(actions.confirmLegacyChangeImport(new FormData(), { skipDuplicates: true, updateExisting: false })).resolves.toEqual({
    ok: false,
    message: '暂未确认变更导入结果，请先查看业务记录后再决定是否重试',
    reference: expect.any(String),
  })
  expect(fetcher).toHaveBeenCalledTimes(1)
  expect(revalidatePath).not.toHaveBeenCalled()
})
