import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  cookies: vi.fn().mockResolvedValue({
    get: vi.fn().mockReturnValue({ value: 'hr-action-token' }),
  }),
  revalidatePath: vi.fn(),
}))

vi.mock('next/headers', () => ({ cookies: mocks.cookies }))
vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidatePath }))

import {
  addNewEmployeeTrainingItem,
  addNewEmployeeTrainingTrainees,
  approvePositionTransferNode,
  batchAnalyzeCandidatesAction,
  batchUpdatePlanItems,
  createAnnualTrainingPlan,
  createCandidateAction,
  createManualNewEmployeeTrainingPlan,
  createOffboardingRecord,
  deleteNewEmployeeTrainingPlan,
  deleteOffboardingRecord,
  fetchDepartureRecords,
  fetchOffboardingRecordsAction,
  generateNewEmployeeTrainingPlan,
  sendCandidateNoticeAction,
  sendOfferEmailAction,
  startNewEmployeeTraining,
  submitPositionTransferApproval,
  syncDepartmentsFromFeishuAction,
  syncOffboardingFromFeishuAction,
  updateNewEmployeeTrainingPlan,
  updateOffboardingRecord,
} from './hr'

function response(data: unknown = { ok: true }): Response {
  return new Response(JSON.stringify({ code: 200, message: 'ok', data }), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

describe('HR migration server-action contracts', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('keeps old/new HR ledgers, notification and training actions on authenticated APIs', async () => {
    const fetchMock = vi.fn().mockImplementation(async () => response())
    vi.stubGlobal('fetch', fetchMock)

    await fetchOffboardingRecordsAction({ employee_id: 'employee-1', keyword: '张', page: 2 })
    await fetchDepartureRecords({ department: '质量', offboarding_type: 'resign', keyword: '张' })
    await createOffboardingRecord({ employee_id: 'employee-1' } as never)
    await updateOffboardingRecord('departure-1', { reason: '个人原因' } as never)
    await deleteOffboardingRecord('departure-1')
    await syncOffboardingFromFeishuAction()

    await createAnnualTrainingPlan({ year: 2026, department: '质量', plan_level: 'department' })
    await batchUpdatePlanItems('plan-1', { items: [] })
    await generateNewEmployeeTrainingPlan({ employee_id: 'employee-1' } as never)
    await createManualNewEmployeeTrainingPlan({ employee_name: '李四' } as never)
    await updateNewEmployeeTrainingPlan('plan-1', { status: 'draft' } as never)
    await addNewEmployeeTrainingItem('plan-1', { title: 'GMP' } as never)
    await startNewEmployeeTraining('plan-1', { item_ids: [] } as never)
    await addNewEmployeeTrainingTrainees('plan-1', { item_ids: [], additional_trainees: [] })
    await deleteNewEmployeeTrainingPlan('plan-1')

    await sendCandidateNoticeAction('candidate-1', 'interview')
    await sendOfferEmailAction({
      candidate_id: 'candidate-1',
      to_email: 'candidate@example.com',
      subject: '录用通知',
      body: '您好',
    })
    await batchAnalyzeCandidatesAction(['candidate-1'])
    await submitPositionTransferApproval('transfer-1', true, { manager: 'user-1' })
    await approvePositionTransferNode('transfer-1', '同意')
    await syncDepartmentsFromFeishuAction(false)

    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/hr/departure-records'))).toBe(true)
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/hr/new-employee-training/plans/generate'))).toBe(true)
    expect(fetchMock.mock.calls.some(([url, init]) =>
      String(url).includes('/hr/candidates/candidate-1/send-notice') && init?.method === 'POST',
    )).toBe(true)
    expect(fetchMock.mock.calls.every(([, init]) => {
      const headers = init?.headers as Record<string, string> | undefined
      return headers?.Authorization === 'Bearer hr-action-token'
    })).toBe(true)
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/hr/offboarding')
  })

  it('keeps unsupported candidate upload actions explicit instead of silently succeeding', async () => {
    await expect(createCandidateAction(new FormData())).rejects.toThrow('功能尚未实现')
  })
})
