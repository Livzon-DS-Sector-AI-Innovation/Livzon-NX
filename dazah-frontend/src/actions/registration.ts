'use server'

import { revalidatePath } from 'next/cache'
import { registrationProjectLedgerSheets } from '@/lib/registration-project-ledger'
import {
  serverApiPost,
  serverApiPut,
  serverApiPatch,
  serverApiDelete,
  serverApiPostFormData,
  serverApiGet,
} from '@/lib/api/server/registration'
import {
  AuthorizationFdaEntryInput,
  AuthorizationFdaEntryUpdateInput,
  AuthorizationLedgerMainCreateInput,
  AuthorizationLedgerMainUpdateInput,
  AuthorizationLedgerUpdateCreateInput,
  AuthorizationLedgerUpdateUpdateInput,
  AuthorizationLetterCreateInput,
  CertificateEntryInput,
  CertificateWorkbookImportResult,
  DeclarationProgressEntryInput,
  DeclarationProgressWorkbookImportResult,
  CertificateReminderSettingInput,
  FeeEntryCreate,
  FeeEntryUpdate,
  InspectionContactCreate,
  InspectionContactUpdate,
  KnowledgeArticle,
  KnowledgeArticleCreate,
  KnowledgeArticleUpdate,
  KnowledgeCategoryCreate,
  KnowledgeCategoryUpdate,
  KnowledgeCommentCreate,
  KnowledgeCommentUpdate,
  ProjectLedgerEntryInput,
  ProjectLedgerWorkbookImportResult,
  ReferenceStandardListItem,
  SupplementaryReplyListItem,
} from '@/types/registration'

type PaginatedServerResult<T> = {
  code: number
  message: string
  data: T[]
  meta?: { page?: number; page_size?: number; total?: number }
}

function appendOptionalFormValues(formData: FormData, values: Record<string, unknown>) {
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') formData.append(key, String(value))
  })
}

export async function fetchReferenceStandardsServer(params?: {
  drug_name?: string
  page?: number
  page_size?: number
}): Promise<PaginatedServerResult<ReferenceStandardListItem>> {
  const search = new URLSearchParams()
  if (params?.drug_name) search.set('drug_name', params.drug_name)
  search.set('page', String(params?.page || 1))
  search.set('page_size', String(params?.page_size || 20))
  return serverApiGet<ReferenceStandardListItem[]>(`/api/v1/registration/reference-standards?${search}`)
}

export async function generateReferenceStandard(formData: FormData, data: Record<string, unknown>) {
  appendOptionalFormValues(formData, data)
  try {
    await serverApiPostFormData('/api/v1/registration/reference-standards/generate', formData)
    revalidatePath('/registration/reference-standard')
    return { success: true, message: '对照物质说明表生成成功' }
  } catch (error) {
    return { success: false, message: error instanceof Error ? error.message : '生成失败' }
  }
}

export async function deleteReferenceStandardAction(id: string) {
  const result = await serverApiDelete(`/api/v1/registration/reference-standards/${id}`)
  revalidatePath('/registration/reference-standard')
  return result
}

export async function fetchSupplementaryRepliesServer(params?: {
  drug_name?: string
  page?: number
  page_size?: number
}): Promise<PaginatedServerResult<SupplementaryReplyListItem>> {
  const search = new URLSearchParams()
  if (params?.drug_name) search.set('drug_name', params.drug_name)
  search.set('page', String(params?.page || 1))
  search.set('page_size', String(params?.page_size || 20))
  return serverApiGet<SupplementaryReplyListItem[]>(`/api/v1/registration/supplementary-replies?${search}`)
}

export async function generateSupplementaryReply(formData: FormData, data: Record<string, unknown>) {
  appendOptionalFormValues(formData, data)
  try {
    await serverApiPostFormData('/api/v1/registration/supplementary-replies/generate', formData)
    revalidatePath('/registration/supplementary-reply')
    return { success: true, message: '发补回复文档生成成功' }
  } catch (error) {
    return { success: false, message: error instanceof Error ? error.message : '生成失败' }
  }
}

export async function deleteSupplementaryReplyAction(id: string) {
  const result = await serverApiDelete(`/api/v1/registration/supplementary-replies/${id}`)
  revalidatePath('/registration/supplementary-reply')
  return result
}

export async function generateAuthorizationLetter(
  formData: FormData,
  data: AuthorizationLetterCreateInput
): Promise<{ success: boolean; message: string; data?: { message?: string } | null }> {
  try {
    // 构建 multipart/form-data
    const submitData = new FormData()
    submitData.append('template', formData.get('template') as File)
    submitData.append('product_name', data.product_name)
    submitData.append('registration_number', data.registration_number)
    submitData.append('preparation_unit', data.preparation_unit)
    submitData.append('preparation_name', data.preparation_name)
    submitData.append('administration_route', data.administration_route)
    if (data.remarks) {
      submitData.append('remarks', data.remarks)
    }
    const replacements = formData.get('replacements')
    if (replacements) {
      submitData.append('replacements', replacements as string)
    }

    const result = await serverApiPostFormData<{ message?: string }>(
      '/api/v1/registration/authorization-letters/generate',
      submitData
    )
    revalidatePath('/registration')
    return {
      success: true,
      message: result?.message || '授权书生成成功',
      data: result,
    }
  } catch (error) {
    return {
      success: false,
      message: error instanceof Error ? error.message : '生成授权书失败',
    }
  }
}

export async function deleteAuthorizationLetter(id: string) {
  const result = await serverApiDelete(`/api/v1/registration/authorization-letters/${id}`)
  revalidatePath('/registration')
  return result
}

export async function createAuthorizationLedgerMain(data: AuthorizationLedgerMainCreateInput) {
  const result = await serverApiPost('/api/v1/registration/authorization-letters/ledger/mains', data)
  revalidatePath('/registration/authorization-letter')
  return result
}

export async function createAuthorizationLedgerUpdate(
  mainId: string,
  data: AuthorizationLedgerUpdateCreateInput
) {
  const result = await serverApiPost(
    `/api/v1/registration/authorization-letters/ledger/mains/${mainId}/updates`,
    data
  )
  revalidatePath('/registration/authorization-letter')
  return result
}

export async function updateAuthorizationLedgerMain(
  id: string,
  data: AuthorizationLedgerMainUpdateInput
) {
  const result = await serverApiPatch(
    `/api/v1/registration/authorization-letters/ledger/mains/${id}`,
    data
  )
  revalidatePath('/registration/authorization-letter')
  return result
}

export async function updateAuthorizationLedgerUpdate(
  id: string,
  data: AuthorizationLedgerUpdateUpdateInput
) {
  const result = await serverApiPatch(
    `/api/v1/registration/authorization-letters/ledger/updates/${id}`,
    data
  )
  revalidatePath('/registration/authorization-letter')
  return result
}

export async function deleteAuthorizationLedgerMain(id: string) {
  const result = await serverApiDelete(
    `/api/v1/registration/authorization-letters/ledger/mains/${id}`
  )
  revalidatePath('/registration/authorization-letter')
  return result
}

export async function deleteAuthorizationLedgerUpdate(id: string) {
  const result = await serverApiDelete(
    `/api/v1/registration/authorization-letters/ledger/updates/${id}`
  )
  revalidatePath('/registration/authorization-letter')
  return result
}

export async function createAuthorizationFdaEntry(data: AuthorizationFdaEntryInput) {
  const result = await serverApiPost('/api/v1/registration/authorization-letters/fda', data)
  revalidatePath('/registration/authorization-letter')
  return result
}

export async function updateAuthorizationFdaEntry(
  id: string,
  data: AuthorizationFdaEntryUpdateInput
) {
  const result = await serverApiPut(
    `/api/v1/registration/authorization-letters/fda/${id}`,
    data
  )
  revalidatePath('/registration/authorization-letter')
  return result
}

export async function deleteAuthorizationFdaEntry(id: string) {
  const result = await serverApiDelete(
    `/api/v1/registration/authorization-letters/fda/${id}`
  )
  revalidatePath('/registration/authorization-letter')
  return result
}

export async function createCertificateEntry(data: CertificateEntryInput) {
  const result = await serverApiPost('/api/v1/registration/certificate-management/entries', data)
  revalidatePath('/registration/certificate-management')
  revalidatePath(`/registration/certificate-management/${data.sheet_key}`)
  return result
}

export async function updateCertificateEntry(
  id: string,
  sheetKey: string,
  data: Partial<CertificateEntryInput>
) {
  const result = await serverApiPut(
    `/api/v1/registration/certificate-management/entries/${id}`,
    data
  )
  revalidatePath('/registration/certificate-management')
  revalidatePath(`/registration/certificate-management/${sheetKey}`)
  return result
}

export async function deleteCertificateEntry(id: string, sheetKey: string) {
  const result = await serverApiDelete(
    `/api/v1/registration/certificate-management/entries/${id}`
  )
  revalidatePath('/registration/certificate-management')
  revalidatePath(`/registration/certificate-management/${sheetKey}`)
  return result
}

export async function updateCertificateReminderSettings(
  data: CertificateReminderSettingInput
) {
  const result = await serverApiPut(
    '/api/v1/registration/certificate-management/reminder-settings',
    data
  )
  revalidatePath('/registration/certificate-management')
  return result
}

export async function importCertificateWorkbook(formData: FormData) {
  const result = await serverApiPostFormData<CertificateWorkbookImportResult>(
    '/api/v1/registration/certificate-management/workbook/import',
    formData
  )
  revalidatePath('/registration/certificate-management')
  return result
}

export async function createProjectLedgerEntry(data: ProjectLedgerEntryInput) {
  const result = await serverApiPost('/api/v1/registration/project-ledger/entries', data)
  revalidatePath('/registration/project-ledger')
  revalidatePath(`/registration/project-ledger/${data.sheet_key}`)
  return result
}

export async function updateProjectLedgerEntry(
  recordId: string,
  data: ProjectLedgerEntryInput
) {
  const result = await serverApiPut(
    `/api/v1/registration/project-ledger/entries/${recordId}`,
    data
  )
  revalidatePath('/registration/project-ledger')
  revalidatePath(`/registration/project-ledger/${data.sheet_key}`)
  return result
}

export async function createProjectLedgerSubRecord(
  recordId: string,
  data: ProjectLedgerEntryInput
) {
  const result = await serverApiPost(
    `/api/v1/registration/project-ledger/entries/${recordId}/sub-records`,
    data
  )
  revalidatePath('/registration/project-ledger')
  revalidatePath(`/registration/project-ledger/${data.sheet_key}`)
  return result
}

export async function deleteProjectLedgerEntry(recordId: string, sheetKey: string) {
  const result = await serverApiDelete(
    `/api/v1/registration/project-ledger/entries/${recordId}`
  )
  revalidatePath('/registration/project-ledger')
  revalidatePath(`/registration/project-ledger/${sheetKey}`)
  return result
}

export async function importProjectLedgerWorkbook(formData: FormData) {
  const result = await serverApiPostFormData<ProjectLedgerWorkbookImportResult>(
    '/api/v1/registration/project-ledger/workbook/import',
    formData
  )
  revalidatePath('/registration/project-ledger')
  for (const sheet of registrationProjectLedgerSheets) {
    revalidatePath(sheet.path)
  }
  return result
}

export async function createDeclarationProgressEntry(data: DeclarationProgressEntryInput) {
  const result = await serverApiPost(
    '/api/v1/registration/declaration-progress/entries',
    data
  )
  revalidatePath('/registration/declaration-progress')
  revalidatePath(`/registration/declaration-progress/${data.sheet_key}`)
  return result
}

export async function updateDeclarationProgressEntry(
  recordId: string,
  data: DeclarationProgressEntryInput
) {
  const result = await serverApiPut(
    `/api/v1/registration/declaration-progress/entries/${recordId}`,
    data
  )
  revalidatePath('/registration/declaration-progress')
  revalidatePath(`/registration/declaration-progress/${data.sheet_key}`)
  return result
}

export async function createDeclarationProgressSubRecord(
  recordId: string,
  data: DeclarationProgressEntryInput
) {
  const result = await serverApiPost(
    `/api/v1/registration/declaration-progress/entries/${recordId}/sub-records`,
    data
  )
  revalidatePath('/registration/declaration-progress')
  revalidatePath(`/registration/declaration-progress/${data.sheet_key}`)
  return result
}

export async function deleteDeclarationProgressEntry(recordId: string, sheetKey: string) {
  const result = await serverApiDelete(
    `/api/v1/registration/declaration-progress/entries/${recordId}`
  )
  revalidatePath('/registration/declaration-progress')
  revalidatePath(`/registration/declaration-progress/${sheetKey}`)
  return result
}

export async function importDeclarationProgressWorkbook(formData: FormData) {
  const result = await serverApiPostFormData<DeclarationProgressWorkbookImportResult>(
    '/api/v1/registration/declaration-progress/workbook/import',
    formData
  )
  revalidatePath('/registration/declaration-progress')
  return result
}

// ── Fee actions ────────────────────────────────────────────────────────

export async function createFeeEntry(data: FeeEntryCreate) {
  const result = await serverApiPost(
    '/api/v1/registration/fees/entries',
    data
  )
  revalidatePath('/registration/fees')
  revalidatePath('/registration/fees/ledger')
  revalidatePath('/registration/fees/contacts')
  return result
}

export async function updateFeeEntry(id: string, data: FeeEntryUpdate) {
  const result = await serverApiPut(
    `/api/v1/registration/fees/entries/${id}`,
    data
  )
  revalidatePath('/registration/fees')
  revalidatePath('/registration/fees/ledger')
  return result
}

export async function deleteFeeEntry(id: string) {
  const result = await serverApiDelete(
    `/api/v1/registration/fees/entries/${id}`
  )
  revalidatePath('/registration/fees')
  revalidatePath('/registration/fees/ledger')
  return result
}

// ── Knowledge actions ──────────────────────────────────────────────────

export async function createKnowledgeCategory(data: KnowledgeCategoryCreate) {
  const result = await serverApiPost(
    '/api/v1/registration/knowledge/categories',
    data
  )
  revalidatePath('/registration/knowledge')
  return result
}

export async function updateKnowledgeCategory(id: string, data: KnowledgeCategoryUpdate) {
  const result = await serverApiPut(
    `/api/v1/registration/knowledge/categories/${id}`,
    data
  )
  revalidatePath('/registration/knowledge')
  return result
}

export async function deleteKnowledgeCategory(id: string) {
  const result = await serverApiDelete(
    `/api/v1/registration/knowledge/categories/${id}`
  )
  revalidatePath('/registration/knowledge')
  return result
}

export async function createKnowledgeArticle(data: KnowledgeArticleCreate): Promise<KnowledgeArticle | null> {
  const result = await serverApiPost<KnowledgeArticle>(
    '/api/v1/registration/knowledge/articles',
    data
  )
  revalidatePath('/registration/knowledge')
  return result
}

export async function updateKnowledgeArticle(id: string, data: KnowledgeArticleUpdate) {
  const result = await serverApiPut(
    `/api/v1/registration/knowledge/articles/${id}`,
    data
  )
  revalidatePath('/registration/knowledge')
  return result
}

export async function deleteKnowledgeArticle(id: string) {
  const result = await serverApiDelete(
    `/api/v1/registration/knowledge/articles/${id}`
  )
  revalidatePath('/registration/knowledge')
  return result
}

// ── Inspection contact actions ─────────────────────────────────────────

export async function createInspectionContact(data: InspectionContactCreate) {
  const result = await serverApiPost(
    '/api/v1/registration/fees/inspection-contacts',
    data
  )
  revalidatePath('/registration/fees')
  revalidatePath('/registration/fees/contacts')
  return result
}

export async function updateInspectionContact(id: string, data: InspectionContactUpdate) {
  const result = await serverApiPut(
    `/api/v1/registration/fees/inspection-contacts/${id}`,
    data
  )
  revalidatePath('/registration/fees')
  revalidatePath('/registration/fees/contacts')
  return result
}

export async function deleteInspectionContact(id: string) {
  const result = await serverApiDelete(
    `/api/v1/registration/fees/inspection-contacts/${id}`
  )
  revalidatePath('/registration/fees')
  revalidatePath('/registration/fees/contacts')
  return result
}

// ── Knowledge comment actions ──────────────────────────────────────────

export async function createKnowledgeComment(articleId: string, data: KnowledgeCommentCreate) {
  const result = await serverApiPost(
    `/api/v1/registration/knowledge/articles/${articleId}/comments`,
    data
  )
  revalidatePath(`/registration/knowledge/${articleId}`)
  return result
}

export async function updateKnowledgeComment(id: string, data: KnowledgeCommentUpdate) {
  const result = await serverApiPut(
    `/api/v1/registration/knowledge/comments/${id}`,
    data
  )
  revalidatePath('/registration/knowledge')
  return result
}

export async function deleteKnowledgeComment(id: string, articleId: string) {
  const result = await serverApiDelete(
    `/api/v1/registration/knowledge/comments/${id}`
  )
  revalidatePath(`/registration/knowledge/${articleId}`)
  return result
}

export async function generateAttachmentSummary(attachmentId: string, articleId: string) {
  const result = await serverApiPost(
    `/api/v1/registration/knowledge/attachments/${attachmentId}/summarize`,
    {}
  )
  revalidatePath(`/registration/knowledge/${articleId}`)
  return result
}

export async function uploadKnowledgeAttachment(articleId: string, formData: FormData) {
  const result = await serverApiPostFormData(
    `/api/v1/registration/knowledge/articles/${articleId}/attachments`,
    formData
  )
  revalidatePath(`/registration/knowledge/${articleId}`)
  return result
}

export async function deleteKnowledgeAttachment(attachmentId: string, articleId: string) {
  const result = await serverApiDelete(
    `/api/v1/registration/knowledge/attachments/${attachmentId}`
  )
  revalidatePath(`/registration/knowledge/${articleId}`)
  return result
}

export async function extractArticleFromFile(formData: FormData) {
  const result = await serverApiPostFormData(
    '/api/v1/registration/knowledge/articles/extract',
    formData
  )
  return result
}
