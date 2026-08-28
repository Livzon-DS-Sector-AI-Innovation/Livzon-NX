import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  cookies: vi.fn().mockResolvedValue({
    get: vi.fn().mockReturnValue({ value: 'registration-action-token' }),
  }),
  revalidatePath: vi.fn(),
}))

vi.mock('next/headers', () => ({ cookies: mocks.cookies }))
vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidatePath }))

import {
  createAuthorizationFdaEntry,
  updateAuthorizationFdaEntry,
  deleteAuthorizationFdaEntry,
  deleteAuthorizationLetter,
  deleteReferenceStandardAction,
  deleteSupplementaryReplyAction,
  createAuthorizationLedgerMain,
  createAuthorizationLedgerUpdate,
  createCertificateEntry,
  createDeclarationProgressEntry,
  createDeclarationProgressSubRecord,
  createFeeEntry,
  createInspectionContact,
  createKnowledgeArticle,
  createKnowledgeCategory,
  createKnowledgeComment,
  createProjectLedgerEntry,
  createProjectLedgerSubRecord,
  deleteAuthorizationLedgerMain,
  deleteAuthorizationLedgerUpdate,
  deleteCertificateEntry,
  deleteDeclarationProgressEntry,
  deleteFeeEntry,
  deleteInspectionContact,
  deleteKnowledgeArticle,
  deleteKnowledgeCategory,
  deleteKnowledgeComment,
  deleteKnowledgeAttachment,
  deleteProjectLedgerEntry,
  generateAttachmentSummary,
  generateAuthorizationLetter,
  generateReferenceStandard,
  generateSupplementaryReply,
  extractArticleFromFile,
  importCertificateWorkbook,
  importDeclarationProgressWorkbook,
  importProjectLedgerWorkbook,
  updateAuthorizationLedgerMain,
  updateAuthorizationLedgerUpdate,
  updateCertificateEntry,
  updateCertificateReminderSettings,
  updateDeclarationProgressEntry,
  updateFeeEntry,
  updateInspectionContact,
  updateKnowledgeArticle,
  updateKnowledgeCategory,
  updateKnowledgeComment,
  updateProjectLedgerEntry,
  uploadKnowledgeAttachment,
  fetchProductsServer,
  fetchSupplementaryRepliesServer,
} from './registration'

function response(data: unknown = { ok: true }): Response {
  return new Response(JSON.stringify({ code: 200, message: 'ok', data }), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

describe('registration migration server-action contracts', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('covers authorization, ledger, certificate, declaration, fee and knowledge writes', async () => {
    const fetchMock = vi.fn().mockImplementation(async () => response())
    vi.stubGlobal('fetch', fetchMock)
    const data = {} as never

    await createAuthorizationLedgerMain(data)
    await createAuthorizationLedgerUpdate('main-1', data)
    await updateAuthorizationLedgerMain('main-1', data)
    await updateAuthorizationLedgerUpdate('update-1', data)
    await deleteAuthorizationLedgerMain('main-1')
    await deleteAuthorizationLedgerUpdate('update-1')
    await createAuthorizationFdaEntry(data)
    await updateAuthorizationFdaEntry('fda-1', data)
    await deleteAuthorizationFdaEntry('fda-1')
    await deleteReferenceStandardAction('standard-1')
    await generateSupplementaryReply(new FormData(), { product_name: '产品A' })
    await deleteSupplementaryReplyAction('reply-1')

    await createCertificateEntry({ sheet_key: 'domestic-gmp' } as never)
    await updateCertificateEntry('certificate-1', 'domestic-gmp', data)
    await deleteCertificateEntry('certificate-1', 'domestic-gmp')
    await importCertificateWorkbook(new FormData())
    await updateCertificateReminderSettings({ enabled: true } as never)

    await createProjectLedgerEntry({ sheet_key: 'domestic-standalone-review' } as never)
    await updateProjectLedgerEntry('project-1', { sheet_key: 'domestic-standalone-review' } as never)
    await createProjectLedgerSubRecord('project-1', { sheet_key: 'domestic-standalone-review' } as never)
    await deleteProjectLedgerEntry('project-1', 'domestic-standalone-review')
    await importProjectLedgerWorkbook(new FormData())

    await createDeclarationProgressEntry({ sheet_key: 'gmp-projects' } as never)
    await updateDeclarationProgressEntry('declaration-1', { sheet_key: 'gmp-projects' } as never)
    await createDeclarationProgressSubRecord('declaration-1', { sheet_key: 'gmp-projects' } as never)
    await deleteDeclarationProgressEntry('declaration-1', 'gmp-projects')
    await importDeclarationProgressWorkbook(new FormData())

    await createFeeEntry(data)
    await updateFeeEntry('fee-1', data)
    await deleteFeeEntry('fee-1')
    await createInspectionContact(data)
    await updateInspectionContact('contact-1', data)
    await deleteInspectionContact('contact-1')

    await createKnowledgeCategory(data)
    await updateKnowledgeCategory('category-1', data)
    await deleteKnowledgeCategory('category-1')
    await createKnowledgeArticle(data)
    await updateKnowledgeArticle('article-1', data)
    await deleteKnowledgeArticle('article-1')
    await createKnowledgeComment('article-1', data)
    await updateKnowledgeComment('comment-1', data)
    await deleteKnowledgeComment('comment-1', 'article-1')
    await generateAttachmentSummary('attachment-1', 'article-1')
    await uploadKnowledgeAttachment('article-1', new FormData())
    await deleteKnowledgeAttachment('attachment-1', 'article-1')
    await extractArticleFromFile(new FormData())

    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/authorization-letters/ledger/mains'))).toBe(true)
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/certificate-management/workbook/import'))).toBe(true)
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/knowledge/articles/article-1/attachments'))).toBe(true)
    expect(fetchMock.mock.calls.every(([, init]) => {
      const headers = init?.headers as Record<string, string> | undefined
      return headers?.Authorization === 'Bearer registration-action-token'
    })).toBe(true)
  })

  it('covers registration generation catches and protected delete/list failures', async () => {
    const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ detail: '无权限执行注册操作' }), {
      status: 403,
      headers: { 'content-type': 'application/json' },
    }))
    vi.stubGlobal('fetch', fetchMock)
    const formData = new FormData()
    formData.append('template', new File(['template'], 'template.docx'))
    const input = {
      product_name: '产品A', registration_number: 'REG-1', preparation_unit: '机构A',
      preparation_name: '张三', administration_route: '口服', remarks: '备注',
    } as never

    await expect(fetchProductsServer()).rejects.toThrow()
    await expect(fetchSupplementaryRepliesServer({ drug_name: '产品A', page: 2, page_size: 5 })).rejects.toThrow()
    await expect(deleteReferenceStandardAction('standard-1')).rejects.toThrow()
    await expect(deleteSupplementaryReplyAction('reply-1')).rejects.toThrow()
    await expect(deleteAuthorizationLetter('letter-1')).rejects.toThrow()
    await expect(generateReferenceStandard(formData, { product_name: '产品A' })).resolves.toMatchObject({ success: false })
    await expect(generateSupplementaryReply(formData, { product_name: '产品A' })).resolves.toMatchObject({ success: false })
    await expect(generateAuthorizationLetter(formData, input)).resolves.toMatchObject({ success: false })
    expect(fetchMock).toHaveBeenCalled()
  })
})
