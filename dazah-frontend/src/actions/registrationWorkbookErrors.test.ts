import { afterEach, describe, expect, it, vi } from 'vitest'

const { revalidatePath } = vi.hoisted(() => ({ revalidatePath: vi.fn() }))
vi.mock('next/cache', () => ({ revalidatePath }))
vi.mock('@/lib/auth', () => ({
  getAuthHeaders: vi.fn(async () => ({ 'Content-Type': 'application/json', 'X-Dazah-Page-Key': 'registration' })),
}))

import { registrationProjectLedgerSheets } from '@/lib/registration-project-ledger'
import {
  importCertificateWorkbook,
  importDeclarationProgressWorkbook,
  importProjectLedgerWorkbook,
} from './registration'

const imports = [
  ['certificate-management', importCertificateWorkbook],
  ['project-ledger', importProjectLedgerWorkbook],
  ['declaration-progress', importDeclarationProgressWorkbook],
] as const

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  revalidatePath.mockClear()
})

describe.each(imports)('%s workbook import', (ledger, importWorkbook) => {
  it.each([
    [401, '登录已失效，请重新登录'],
    [403, '没有执行此操作的权限，请联系管理员'],
    [413, '文件过大，请缩小文件后重试'],
    [422, '填写内容有误，请检查后重试'],
  ])('uses the default prompt for HTTP %i', async (status, message) => {
    vi.stubGlobal('fetch', vi.fn(async () => Response.json({
      message: '内部错误堆栈',
      detail: { error_code: 'UNRECOGNIZED_CODE' },
    }, { status })))
    expect(await importWorkbook(new FormData())).toEqual({ ok: false, message })
    expect(revalidatePath).not.toHaveBeenCalled()
  })

  it('uses the stable template code even if upstream text changes', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Response.json({
      message: 'replacement internal text',
      detail: { error_code: 'REGISTRATION_WORKBOOK_TEMPLATE_MISMATCH' },
    }, { status: 422 })))
    expect(await importWorkbook(new FormData())).toEqual({
      ok: false,
      message: '工作簿与台账模板不匹配，请使用对应模板并保留子表名称和表头',
    })
  })

  it('keeps multipart encoding and refreshes only after accepting the import', async () => {
    const data = { workbook_name: 'test.xlsx' }
    const fetchMock = vi.fn<typeof fetch>(async () => Response.json({ code: 200, data }))
    vi.stubGlobal('fetch', fetchMock)
    const formData = new FormData()
    formData.append('file', new File(['workbook'], 'test.xlsx'))
    expect(await importWorkbook(formData)).toEqual({ ok: true, data })
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toContain(`/api/v1/registration/${ledger}/workbook/import`)
    expect(init?.method).toBe('POST')
    expect(init?.body).toBe(formData)
    expect(new Headers(init?.headers).get('Content-Type')).toBeNull()
    expect(new Headers(init?.headers).get('X-Dazah-Page-Key')).toBe('registration')
    expect(revalidatePath).toHaveBeenCalledWith(`/registration/${ledger}`)
    if (ledger === 'project-ledger') {
      for (const sheet of registrationProjectLedgerSheets) {
        expect(revalidatePath).toHaveBeenCalledWith(sheet.path)
      }
    }
  })
})

it('returns an unknown import outcome with a support reference when the response is lost', async () => {
  vi.spyOn(console, 'error').mockImplementation(() => {})
  const fetchMock = vi.fn().mockRejectedValue(new Error('private server address'))
  vi.stubGlobal('fetch', fetchMock)
  expect(await importCertificateWorkbook(new FormData())).toEqual({
    ok: false,
    message: '暂未确认药政证书台账导入结果，请先查看业务记录后再决定是否重试',
    reference: expect.any(String),
  })
  expect(fetchMock).toHaveBeenCalledTimes(1)
  expect(revalidatePath).not.toHaveBeenCalled()
})
