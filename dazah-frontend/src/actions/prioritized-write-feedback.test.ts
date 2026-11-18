import { afterEach, expect, it, vi } from 'vitest'
import { revalidatePath } from 'next/cache'
import {
  approvePurchaseRequest, importPurchaseRequestTable, importSupplierTable,
  rejectPurchaseRequest, submitPurchaseRequest,
} from './purchasing'
import {
  batchImportHistoricalDeviations, uploadDeviationWorkbenchAttachment, uploadHistoricalDeviationAttachment,
} from './quality-deviation-workbench'
import { approvePilotWorkflowStep, uploadPilotWorkflowDocument } from './rd/research'

vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))
vi.mock('@/lib/auth', () => ({
  getAuthHeaders: async () => ({ Authorization: 'Bearer fixture', 'Content-Type': 'application/json' }),
}))

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  vi.clearAllMocks()
})

const approval = {
  approval_role: 'department_head', approver_name: '测试审批人', opinion: '同意', result: 'approved',
} as const

it.each([
  [() => importPurchaseRequestTable(new FormData()), 422, 'PROCUREMENT_IMPORT_TABLE_INVALID', '无法读取采购申请表格，请使用有效的采购申请模板重新上传'],
  [() => importSupplierTable(new FormData()), 415, null, '文件格式不受支持，请检查后重试'],
  [() => importSupplierTable(new FormData()), 403, 'PROCUREMENT_IMPORT_TABLE_INVALID', '没有执行此操作的权限，请联系管理员'],
  [() => submitPurchaseRequest('req-1'), 422, 'PROCUREMENT_SUBMIT_ITEMS_MISSING', '请至少添加一条采购明细后重新提交'],
  [() => submitPurchaseRequest('req-1'), 422, 'PROCUREMENT_SUBMIT_AMOUNT_MISMATCH', '明细金额与数量乘以单价不一致，请核对后重新提交'],
  [() => approvePurchaseRequest('req-1', approval), 409, null, '数据已发生变化，请刷新后重试'],
  [() => rejectPurchaseRequest('req-1', { ...approval, result: 'rejected' }), 401, null, '登录已失效，请重新登录'],
  [() => batchImportHistoricalDeviations(new FormData()), 400, 'QUALITY_HISTORICAL_DEVIATION_BATCH_LIMIT', '本次附件数量过多，请分批导入'],
  [() => batchImportHistoricalDeviations(new FormData()), 400, 'UNKNOWN', '请求内容有误，请检查后重试'],
  [() => uploadHistoricalDeviationAttachment('history-1', new FormData()), 404, null, '请求的内容不存在或已被删除，请刷新后重试'],
  [() => uploadDeviationWorkbenchAttachment(new FormData()), 415, null, '文件格式不受支持，请检查后重试'],
  [() => approvePilotWorkflowStep('pilot-1'), 409, null, '数据已发生变化，请刷新后重试'],
  [() => uploadPilotWorkflowDocument('pilot-1', new File(['file'], 'sample.docx')), 413, null, '文件过大，请缩小文件后重试'],
] as const)('maps action %s HTTP %i safely', async (call, status, code, message) => {
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({
    message: '上游内部详情', detail: code ? { error_code: code } : null,
  }), { status }))
  vi.stubGlobal('fetch', fetcher)
  await expect(call()).resolves.toEqual({ ok: false, message })
  expect(fetcher).toHaveBeenCalledTimes(1)
  expect(revalidatePath).not.toHaveBeenCalled()
})

it('keeps request credentials and multipart headers for pilot upload', async () => {
  const data = { filename: 'sample.docx', path: 'fixture.docx' }
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ data })))
  vi.stubGlobal('fetch', fetcher)
  const file = new File(['file'], 'sample.docx')
  await expect(uploadPilotWorkflowDocument('pilot-1', file)).resolves.toEqual({ ok: true, data })
  const [, request] = fetcher.mock.calls[0]
  expect(request.headers).toEqual({ Authorization: 'Bearer fixture' })
  expect(request.body.get('file').name).toBe(file.name)
  expect(revalidatePath).toHaveBeenCalledWith('/rd/pilot-workflow/pilot-1')
})

it('reports an ambiguous supplier overwrite without submitting again', async () => {
  vi.spyOn(console, 'error').mockImplementation(() => {})
  const fetcher = vi.fn().mockRejectedValue(new Error('private network error'))
  vi.stubGlobal('fetch', fetcher)
  await expect(importSupplierTable(new FormData())).resolves.toEqual({
    ok: false,
    message: '暂未确认供应商清单导入结果，请先查看业务记录后再决定是否重试',
    reference: expect.any(String),
  })
  expect(fetcher).toHaveBeenCalledTimes(1)
})
