/* @vitest-environment happy-dom */

import { beforeEach, describe, expect, it, vi } from 'vitest'

const deps = vi.hoisted(() => ({
  fetch: vi.fn(),
  revalidatePath: vi.fn(),
  getAuthHeaders: vi.fn(async () => ({ Authorization: 'Bearer test' })),
}))

vi.mock('next/cache', () => ({ revalidatePath: deps.revalidatePath }))
vi.mock('next/headers', () => ({
  cookies: vi.fn(async () => ({ get: () => undefined })),
}))
vi.mock('@/lib/auth', () => ({ getAuthHeaders: deps.getAuthHeaders }))
vi.mock('@/lib/server-api', () => ({
  getServerApiBaseUrl: () => 'http://backend.test',
  getBackendFallbackUrls: () => [],
}))

function okResponse(data: unknown = {}) {
  return new Response(JSON.stringify({ data }), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

const formData = () => {
  const form = new FormData()
  form.append('file', new File(['test'], 'import.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }))
  return form
}

const payload = {
  id: 'record-1', record_id: 'record-1', name: '测试记录', title: '测试记录', code: 'TEST-1',
  deviation_id: 'deviation-1', change_id: 'change-1', capa_id: 'capa-1', product_code: 'LFT',
  department_id: 'dept-1', status: 'draft', field_keys: ['title'], section: 'deviation_analysis',
}

function argsFor(name: string, arity: number): unknown[] {
  if (arity === 0) return []
  if (name === 'fetchLabelVerificationsServer') return [{ page: 1, page_size: 20 }]
  if (name === 'deleteDocumentEntryAttachment') return ['entry-1', 'quality/entry-1/file.pdf']
  if (name === 'syncWarehouseFeishuTablesAction') return [['table-1']]
  if (name === 'saveWarehousePageBindingsAction') return ['raw-summary', [{ resource_id: 'table-1', tab_name: '原辅料', sort_order: 1, is_default: true, is_enabled: true, visible_field_ids: [] }]]
  if (name === 'saveRoleDataScope' || name === 'saveUserDataScope') return ['record-1', 'all', []]
  if (name === 'setRolePermissions' || name === 'assignUserRoles' || name === 'setRoleMenus') return ['record-1', ['permission-1']]
  if (/Import|Attachment|upload.*Attachment|uploadDocument|autoBind/i.test(name)) {
    return [formData(), false, false, 'technical'].slice(0, arity)
  }
  if (/resolveDocumentEntryContent/i.test(name)) return [['SOP-1']]
  if (/batchDelete|Ids|RecordIds|fieldKeys/i.test(name)) {
    return [ ['record-1'], payload, 'technical', false ].slice(0, arity)
  }
  if (/applyQualityAiLog/i.test(name)) return ['record-1', ['title']]
  if (/create|update|save|confirm|close|complete|approve|start|respond|ensure|sync|analyze|suggest|delete|pull|fetch/i.test(name)) {
    return [name.startsWith('create') || name.startsWith('save') ? payload : 'record-1', payload, 'technical', false].slice(0, arity)
  }
  return Array.from({ length: arity }, () => payload)
}

async function exerciseModule(modulePath: string) {
  const loadedModule = await import(modulePath)
  const failures: string[] = []
  for (const [name, value] of Object.entries(loadedModule)) {
    if (typeof value !== 'function' || name === 'default') continue
    try {
      await (value as (...args: unknown[]) => unknown)(...argsFor(name, value.length))
    } catch (error) {
      failures.push(`${name}: ${error instanceof Error ? error.message : String(error)}`)
    }
  }
  expect(failures).toEqual([])
}

describe('migration server action coverage', () => {
  beforeEach(() => {
    deps.fetch.mockReset()
    deps.fetch.mockImplementation(async () => okResponse({
      synced: 1, failed: 0, deleted: 1, record_id: 'record-1', deviation_id: 'deviation-1',
      items: [], rows: [], total: 0, success_count: 1,
    }))
    vi.stubGlobal('fetch', deps.fetch)
    deps.revalidatePath.mockReset()
  })

  it('covers quality action contracts and import/upload paths', async () => {
    await exerciseModule('@/actions/quality')
    await exerciseModule('@/actions/quality-capa')
    await exerciseModule('@/actions/quality-change')
    await exerciseModule('@/actions/quality-deviation')
    expect(deps.fetch).toHaveBeenCalled()
    expect(deps.revalidatePath).toHaveBeenCalled()
  })

  it('covers system permission and warehouse server action contracts', async () => {
    const admin = await import('@/actions/admin')
    const warehouse = await import('@/actions/warehouse')
    for (const [name, value] of Object.entries({ ...admin, ...warehouse })) {
      if (typeof value !== 'function' || name === 'exportPermissions') continue
      await (value as (...args: unknown[]) => unknown)(...argsFor(name, value.length))
    }
    deps.fetch.mockResolvedValueOnce(new Response('permission,csv', {
      status: 200,
      headers: { 'Content-Disposition': 'attachment; filename="permissions.csv"' },
    }))
    const exported = await admin.exportPermissions()
    expect(exported.filename).toBe('permissions.csv')
  })

  it('maps backend action failures without leaking raw responses', async () => {
    deps.fetch.mockResolvedValueOnce(new Response(JSON.stringify({ detail: '权限不足' }), { status: 403, statusText: 'Forbidden' }))
    const { createDeviation } = await import('@/actions/quality')
    await expect(createDeviation(payload as never)).rejects.toThrow('权限不足')
  })
})
