import { afterEach, expect, it, vi } from 'vitest'
vi.mock('@/lib/auth', () => ({ getAuthHeaders: vi.fn().mockResolvedValue({
  Authorization: 'Bearer fixture', 'X-Dazah-Operation-ID': 'fixture-operation', 'Content-Type': 'application/json',
}) }))
vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))
import { uploadWorkOrderImages } from './equipment'
import {
  addPersonnel, assignCategories, assignRoles, createRole, deletePersonnel, deleteRole,
  refreshFeishu, updateRole,
} from './equipment-personnel'
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

it('rejects an empty image selection without sending a work order update', async () => {
  const fetcher = vi.fn()
  vi.stubGlobal('fetch', fetcher)
  const form = new FormData()
  form.append('files', new File([], 'empty.jpg'))

  await expect(uploadWorkOrderImages('fixture-order', form)).resolves.toEqual({
    ok: false, message: '请选择非空图片后重新上传',
  })
  expect(fetcher).not.toHaveBeenCalled()
})

it.each([
  ['更新角色', () => updateRole('role/1', { name: '维修员' }), '/roles/role%2F1', 'PUT', { name: '维修员' }],
  ['删除角色', () => deleteRole('role/1'), '/roles/role%2F1', 'DELETE', undefined],
  ['添加人员', () => addPersonnel({ user_ids: ['user-1'] }), '', 'POST', { user_ids: ['user-1'] }],
  ['移除人员', () => deletePersonnel('user/1'), '/user%2F1', 'DELETE', undefined],
  ['分配角色', () => assignRoles('user/1', { role_ids: ['role-1'] }), '/user%2F1/roles', 'POST', { role_ids: ['role-1'] }],
  ['保存分类', () => assignCategories('user/1', { categories: [] }), '/user%2F1/categories', 'POST', { categories: [] }],
  ['刷新飞书', () => refreshFeishu(), '/refresh-feishu', 'POST', undefined],
] as const)('保留%s的请求契约并处理被拒的写入', async (_, mutate, path, method, body) => {
  const fetcher = vi.fn().mockResolvedValueOnce(Response.json({ message: 'internal authorization failure' }, { status: 403 }))
  vi.stubGlobal('fetch', fetcher)
  vi.mocked(revalidatePath).mockClear()

  await expect(mutate()).resolves.toEqual({ ok: false, message: '没有执行此操作的权限，请联系管理员' })
  expect(fetcher).toHaveBeenCalledWith(
    expect.stringMatching(new RegExp(`/api/v1/equipment/personnel${path}$`)),
    expect.objectContaining({ method, body: body === undefined ? undefined : JSON.stringify(body) }),
  )
  expect(revalidatePath).not.toHaveBeenCalled()
})
