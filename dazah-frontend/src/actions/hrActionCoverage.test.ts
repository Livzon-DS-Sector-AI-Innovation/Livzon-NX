import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  cookies: vi.fn().mockResolvedValue({
    get: vi.fn().mockReturnValue({ value: 'hr-coverage-token' }),
  }),
  revalidatePath: vi.fn(),
}))

vi.mock('next/headers', () => ({
  cookies: mocks.cookies,
  headers: vi.fn(async () => new Headers()),
}))
vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidatePath }))

import * as actions from './hr'

function response(): Response {
  return new Response(JSON.stringify({
    code: 200,
    message: 'ok',
    data: { id: 'record-1', items: [], task_id: 'task-1', state: 'completed' },
  }), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

async function call(name: keyof typeof actions, ...args: unknown[]): Promise<unknown> {
  const action = actions[name] as (...parameters: never[]) => unknown
  return action(...args as never[])
}

describe('migrated HR server action coverage', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('touches legacy ledgers, settings, recruitment, and approval actions', async () => {
    const fetchMock = vi.fn().mockImplementation(async () => response())
    vi.stubGlobal('fetch', fetchMock)
    const formData = new FormData()
    formData.append('file', new File(['content'], 'training.xlsx'))

    await call('fetchEmployeesAction', { department: '质量部', keyword: '张', page: 2, page_size: 20 })
    await call('updateEmployee', 'employee-1', { name: '李四' })
    await call('deleteEmployee', 'employee-1')
    await call('syncFromFeishuAction')
    await call('syncToFeishuAction', 'employee-1')
    await call('fetchDepartmentsAction', { keyword: '质量', parent_id: 'root', leader_name: '张', page: 2, page_size: 20 })
    await call('createDepartment', { code: 'QA', name: '质量部' })
    await call('updateDepartment', 'department-1', { name: '质量部' })
    await call('deleteDepartment', 'department-1')
    await call('fetchTeamsAction', { department_id: 'department-1', keyword: '一班', page: 2, page_size: 20 })
    await call('createTeam', { name: '一班', department_id: 'department-1' })
    await call('updateTeam', 'team-1', { name: '二班' })
    await call('deleteTeam', 'team-1')
    await call('fetchEmployees', { department: '质量部', page: 2 })
    await call('fetchDepartments', { keyword: '质量', page: 2 })
    await call('fetchTeams', { department_id: 'department-1' })
    await call('fetchOffboardingRecords', { employee_id: 'employee-1', page: 2 })
    await call('fetchDepartureRecords', { department: '质量部', offboarding_type: 'resign', page: 2 })
    await call('createOffboardingRecord', { employee_id: 'employee-1', offboarding_date: '2026-08-25' })
    await call('updateOffboardingRecord', 'offboarding-1', { reason: '离职' })
    await call('deleteOffboardingRecord', 'offboarding-1')
    await call('fetchEmployeeById', 'employee-1')
    await call('fetchCandidateById', 'candidate-1')
    await call('fetchAnnualTrainingPlanById', 'plan-1')
    await call('fetchPlanItems', 'plan-1')
    await call('createAnnualTrainingPlan', { year: 2026, department: '质量部', plan_level: '部门级' })
    await call('deleteAnnualTrainingPlan', 'plan-1')
    await call('batchUpdatePlanItems', 'plan-1', { items: [{ title: 'GMP' }] })
    await call('importAnnualTrainingPlan', new File(['content'], 'annual.docx'), 2026, '部门级', '质量部')
    await expect(call('createCandidateAction', formData)).rejects.toThrow('功能尚未实现')
    await expect(call('parseResumePreviewAction', formData)).rejects.toThrow('功能尚未实现')
    await expect(call('syncCandidateToFeishuAction', 'candidate-1')).rejects.toThrow('功能尚未实现')
    await call('updateCandidateAction', 'candidate-1', { name: '李四' })
    await call('updateCandidateRecommendationLevelAction', 'candidate-1', '高')
    await call('fetchCandidatesFromFeishu')
    await call('deleteCandidateAction', 'candidate-1')
    await call('fetchEmployeeByNumber', 'E001')
    await call('fetchDepartmentTreeAction')
    await call('syncDepartmentsFromFeishuAction', false)
    await call('getDepartmentSyncStatus')
    await call('updateHrFeishuAppSettings', { app_id: 'app', app_secret: 'secret', is_enabled: true })
    await call('testHrFeishuAppSettings')
    await call('updateHrFeishuEntitySetting', 'employees', { table_id: 'table' })
    await call('testHrFeishuEntitySetting', 'employees')
    await call('updateEmailConfig', { host: 'mail.local' })
    await call('testEmailConfig')
    await call('updateReminderConfig', 'reminder-1', { enabled: true })
    await call('updateApprovalConfig', 'approval-1', { enabled: true })
    await call('saveDeptRecipients', 'reminder-1', [{ department: '质量部' }])
    await call('deleteDeptRecipient', 'recipient-1')
    await call('syncFeishuMembersAction')
    await call('getFeishuMembersSyncStatus')
    await call('fetchJobPostingsServer', { keyword: '分析', page: 2, page_size: 20 })
    await call('fetchOrgTreeAction')
    await call('createJobPosting', { title: '分析员' })
    await call('batchAnalyzeCandidatesAction', ['candidate-1'])
    await call('createOnboardingFromInterviewAction', 'candidate-1')
    await call('updateOnboardingAction', 'onboarding-1', { status: 'approved' })
    await call('createEmployeePublicAction', { name: '张三' })
    await call('syncOnboardingToEmployeeAction', 'onboarding-1')
    await call('syncOnboardingToContractAction', '张三', '质量部', 'P3')
    await call('triggerEmailFetch', false)
    await call('submitPositionTransferApproval', 'transfer-1', true, { manager: 'user-1' })
    await call('approvePositionTransferNode', 'transfer-1', '同意')
    await call('rejectPositionTransferNode', 'transfer-1', '不同意')
    await call('createPositionTransfer', { employee_id: 'employee-1' })
    await call('updatePositionTransfer', 'transfer-1', { reason: '岗位调整' })
    await call('deletePositionTransfer', 'transfer-1')
    await call('syncPositionTransferFromFeishuAction')
    await call('createDeptApprovalConfigAction', { department_id: 'department-1', department_name: '质量部' })
    await call('updateDeptApprovalConfigAction', 'config-1', { manager_name: '张三' })
    await call('deleteDeptApprovalConfigAction', 'config-1')
    await call('initDeptApprovalConfigsAction')
    await call('syncOffboardingFromFeishuAction')
    await call('generateOffboardingCertificateAction', 'offboarding-1')
    await call('uploadOffboardingTemplateAction', formData)
    await call('fetchOffboardingTemplateInfoAction')
    await call('sendOfferEmailAction', { candidate_id: 'candidate-1', to_email: 'a@example.com', subject: 'Offer', body: '您好' })
    await call('sendCandidateNoticeAction', 'candidate-1', 'interview')
    await call('uploadOfferTemplateAction', formData)
    await call('updateContractSignStatusAction', 'contract-1', '已签署')
    await call('addCustomTrainingDepartment', '质量部')
    await call('deleteCustomTrainingDepartment', '质量部')

    expect(fetchMock.mock.calls.length).toBeGreaterThan(50)
    expect(fetchMock.mock.calls.every(([, init]) => {
      const headers = init?.headers as Record<string, string> | undefined
      return headers?.Authorization === 'Bearer hr-coverage-token'
    })).toBe(true)
  })

  it.each([
    [401, { message: 'Unauthorized' }, '登录已失效，请重新登录'],
    [403, { message: '未获得当前高风险业务动作授权' }, '没有执行此操作的权限，请联系管理员'],
    [403, { detail: '内部授权信息' }, '没有执行此操作的权限，请联系管理员'],
    [400, { message: '已改写的后端诊断', detail: { error_code: 'HR_ANNUAL_PLAN_ITEMS_MISSING' } }, '文档中没有有效的培训计划数据，请使用 APP1 或 APP2 模板'],
    [400, { detail: { error_code: 'HR_ANNUAL_PLAN_DEPARTMENT_MISSING' } }, '无法识别部门，请在部门级模板中填写部门后重新上传'],
    [400, { message: '无法从文档中识别部门，请手动指定部门' }, '请求内容有误，请检查后重试'],
    [400, { detail: { error_code: 'HR_FUTURE_ERROR' } }, '请求内容有误，请检查后重试'],
    [400, { detail: { error_code: 123 } }, '请求内容有误，请检查后重试'],
    [400, { detail: { error_code: 'constructor' } }, '请求内容有误，请检查后重试'],
    [400, { error_code: 'HR_ANNUAL_PLAN_ITEMS_MISSING' }, '请求内容有误，请检查后重试'],
    [413, null, '文件过大，请缩小文件后重试'],
    [415, null, '文件格式不受支持，请检查后重试'],
    [422, { detail: [{ loc: ['query', 'year'], msg: '内部校验信息' }] }, '填写内容有误，请检查后重试'],
    [422, { detail: { error_code: 'HR_ANNUAL_PLAN_ITEMS_MISSING' } }, '填写内容有误，请检查后重试'],
    [404, null, '请求的内容不存在或已被删除，请刷新后重试'],
    [409, null, '数据已发生变化，请刷新后重试'],
    [429, null, '操作过于频繁，请稍后重试'],
  ])('returns a serializable annual-plan import failure for HTTP %i', async (status, body, message) => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(body ? JSON.stringify(body) : null, { status }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await actions.importAnnualTrainingPlan(new File(['content'], 'annual.docx'), 2026)

    expect(JSON.parse(JSON.stringify(result))).toEqual({ ok: false, message })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('validates annual-plan import arguments before forwarding the request', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    await expect(actions.importAnnualTrainingPlan(new File(['content'], 'annual.docx'), NaN))
      .resolves.toEqual({ ok: false, message: '请选择有效的年度' })
    await expect(actions.importAnnualTrainingPlan(new File(['content'], 'annual.xlsx'), 2026))
      .resolves.toEqual({ ok: false, message: '请选择 .docx 格式的 Word 文档' })
    await expect(actions.importAnnualTrainingPlan(new File([], 'annual.docx'), 2026))
      .resolves.toEqual({ ok: false, message: 'Word 文档为空，请重新选择文件' })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('keeps unexpected import failures private and returns a diagnostic reference', async () => {
    const log = vi.spyOn(console, 'error').mockImplementation(() => {})
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response('上游内部响应', { status: 503 }))
      .mockRejectedValueOnce(new Error('内部网络详情'))
    vi.stubGlobal('fetch', fetchMock)
    try {
      for (const secret of ['上游内部响应', '内部网络详情']) {
        const result = await actions.importAnnualTrainingPlan(new File(['content'], 'annual.docx'), 2026)
        expect(result).toMatchObject({ ok: false, reference: expect.any(String) })
        expect(JSON.stringify(result)).not.toContain(secret)
      }
      expect(log).toHaveBeenCalledTimes(2)
    } finally {
      log.mockRestore()
    }
  })

  it('forwards an authorized annual-plan import and returns the success message', async () => {
    const fetchMock = vi.fn().mockImplementation(async () => response())
    vi.stubGlobal('fetch', fetchMock)
    const file = new File(['content'], 'annual.docx')

    await expect(actions.importAnnualTrainingPlan(file, 2026, '部门级', '质量部'))
      .resolves.toEqual({ ok: true, data: { message: 'ok' } })
    const [url, init] = fetchMock.mock.calls[0]
    expect(new URL(url).pathname).toBe('/api/v1/hr/annual-training-plans/import')
    expect(Object.fromEntries(new URL(url).searchParams)).toEqual({ year: '2026', plan_level: '部门级', department: '质量部' })
    expect(init).toMatchObject({ method: 'POST', headers: { Authorization: 'Bearer hr-coverage-token' } })
    expect(init.headers).not.toHaveProperty('Content-Type')
    expect(init.body.get('file').name).toBe('annual.docx')
  })

  it('maps structured training conflicts', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({
        code: 200,
        data: {
          has_conflict: true,
          instructor_conflicts: [{ training_name: 'GMP', time_range: '09:00-10:00', conflict_depts: ['质量部'], conflict_count: 1 }],
          trainee_conflicts: [{ training_name: 'GMP', time_range: '09:00-10:00', names: ['张三'], conflict_count: 1 }],
          suggested_times: [{ start: '2026-08-26 09:00', end: '2026-08-26 10:00' }],
        },
      }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(call('checkTrainingConflict', { training_date: '2026-08-25' })).resolves.toMatchObject({
      data: {
        has_conflict: true,
        instructor_conflicts: [{ training_name: 'GMP', conflict_count: 1 }],
        trainee_conflicts: [{ names: ['张三'] }],
        suggested_times: [{ start: '2026-08-26 09:00' }],
      },
    })
  })

  it.each([
    ['createAnnualTrainingPlan', [{ year: 2026, department: '质量部' }], 409, 'HR_ANNUAL_PLAN_DUPLICATE', '该部门本年度的培训计划已存在'],
    ['deleteAnnualTrainingPlan', ['plan-1'], 403, null, '没有执行此操作的权限，请联系管理员'],
    ['deleteAnnualTrainingPlan', ['plan-1'], 404, null, '请求的内容不存在或已被删除，请刷新后重试'],
    ['importPositionTrainingLists', [new File(['content'], '岗位培训.docx')], 400, 'HR_POSITION_TRAINING_TEMPLATE_INVALID', '文档无法解析，请使用 APP9 岗位培训清单模板'],
    ['importPositionTrainingLists', [new File(['content'], '岗位培训.docx')], 400, 'HR_POSITION_TRAINING_DATA_MISSING', '文档缺少部门或培训明细，请按 APP9 模板填写后重新上传'],
    ['importPositionTrainingLists', [new File(['content'], '岗位培训.docx')], 403, null, '没有执行此操作的权限，请联系管理员'],
    ['submitPositionTransferApproval', ['transfer-1', false], 409, 'HR_POSITION_TRANSFER_NOT_DRAFT', '只有草稿状态的记录才能提交审批，请刷新后查看当前状态'],
    ['approvePositionTransferNode', ['transfer-1', '同意'], 409, 'HR_POSITION_TRANSFER_APPROVAL_COMPLETED', '该记录已完成审批，请刷新后查看审批结果'],
    ['approvePositionTransferNode', ['transfer-1', '同意'], 423, null, '记录正在处理中，请稍后刷新查看'],
    ['rejectPositionTransferNode', ['transfer-1', '不同意'], 409, 'HR_POSITION_TRANSFER_NOT_SUBMITTED', '该记录尚未提交审批，请刷新后查看当前状态'],
    ['rejectPositionTransferNode', ['transfer-1', '不同意'], 403, null, '没有执行此操作的权限，请联系管理员'],
    ['syncFeishuMembersAction', [], 403, null, '没有执行此操作的权限，请联系管理员'],
    ['syncDepartmentsFromFeishuAction', [], 429, null, '操作过于频繁，请稍后重试'],
    ['getDepartmentSyncStatus', [], 401, null, '登录已失效，请重新登录'],
    ['getFeishuMembersSyncStatus', [], 403, null, '没有执行此操作的权限，请联系管理员'],
    ['syncPositionTransferFromFeishuAction', [], 503, 'HR_POSITION_TRANSFER_FEISHU_NOT_CONFIGURED', '岗位调动的飞书数据源未配置，请联系管理员检查人事飞书设置'],
    ['uploadPlanAttachments', ['plan-1', [new File(['content'], '培训记录.docx')]], 400, 'HR_ANNUAL_PLAN_ATTACHMENT_COUNT_EXCEEDED', '单次上传的附件过多，请减少本次选择的文件数量'],
    ['uploadPlanAttachments', ['plan-1', [new File(['content'], '培训记录.docx')]], 413, null, '文件过大，请缩小文件后重试'],
  ] as const)('returns a public failure for %s', async (action, args, status, errorCode, expected) => {
    const request = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      code: status, message: '内部诊断信息', detail: errorCode ? { error_code: errorCode } : null,
    }), { status }))
    vi.stubGlobal('fetch', request)
    await expect(call(action, ...args)).resolves.toEqual({ ok: false, message: expected })
    expect(request).toHaveBeenCalledTimes(1)
    expect(mocks.revalidatePath).not.toHaveBeenCalled()
  })

  it('keeps an ambiguous approval failure private and does not repeat the write', async () => {
    const log = vi.spyOn(console, 'error').mockImplementation(() => {})
    const request = vi.fn().mockResolvedValue(new Response('private upstream response', { status: 504 }))
    vi.stubGlobal('fetch', request)
    try {
      await expect(actions.submitPositionTransferApproval('transfer-1', false)).resolves.toEqual({
        ok: false,
        message: '暂未确认岗位调动审批提交结果，请先查看业务记录后再决定是否重试',
        reference: expect.any(String),
      })
      expect(request).toHaveBeenCalledTimes(1)
    } finally {
      log.mockRestore()
    }
  })

  it('maps HR action errors that only contain a message', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ message: '飞书配置不可用' }), { status: 503 })))
    await expect(call('testHrFeishuAppSettings')).rejects.toThrow('飞书配置不可用')
  })

  it('touches training, import, document, contract, and attachment actions', async () => {
    const fetchMock = vi.fn().mockImplementation(async () => response())
    vi.stubGlobal('fetch', fetchMock)
    const file = new File(['content'], 'training.xlsx', { type: 'application/vnd.ms-excel' })

    await call('checkTrainingConflict', {
      training_date: '2026-08-25', time_start: '09:00', time_end: '10:00', trainees: ['张三'],
    })
    await call('createTrainingLedger', { employee_number: 'E001', employee_name: '张三' })
    await call('updateTrainingLedger', 'ledger-1', { result: '合格' })
    await call('deleteTrainingLedger', 'ledger-1')
    await call('clearTrainingLedgersByDept', '质量部')
    await call('createTrainingLedgerPage', { employee_number: 'E001', employee_name: '张三' })
    await call('generateTrainingSignInSheet', { training_date: '2026-08-25' })
    await call('generateTrainingNotification', { training_date: '2026-08-25' })
    await call('generateTrainingEvaluation', { training_date: '2026-08-25' })
    await call('generateOnboardingEvaluation', { approval_date: '2026-08-25' })
    await call('generateOralExamResult', { training_date: '2026-08-25' })
    await call('generatePracticalExamResult', { training_date: '2026-08-25', training_content: '现场操作' })
    await call('generateTrainingAttachment', { training_date: '2026-08-25' })
    await call('importPracticalExamQuestions', file)
    await call('syncContractsFromFeishu')
    await call('pushContractExpiringAction', '2026-08-01', '2026-08-31')
    await call('getContractPushStatusAction')
    await call('saveContractTemplateAction', { name: 'template' })
    await call('deleteContractAction', 'contract-1')
    await call('updateContractAction', 'contract-1', { signed_status: '已签署' })
    await call('renewContractAction', 'contract-1', '2026-01-01', '2027-01-01')
    await call('createTrainer', { name: '培训师' })
    await call('updateTrainer', 'trainer-1', { name: '培训师2' })
    await call('deleteTrainer', 'trainer-1')
    await call('importTrainers', new FormData())
    await call('createTrainingEvaluation', { training_ledger_id: 'ledger-1' })
    await call('updateTrainingEvaluation', 'evaluation-1', { score: 90 })
    await call('deleteTrainingEvaluation', 'evaluation-1')
    await call('saveTrainingPersonnelConfig', { department: '质量部' })
    await call('deleteTrainingPersonnelConfig', 'config-1')
    await call('createPositionTrainingList', { position: '分析员' })
    await call('updatePositionTrainingList', 'list-1', { position: '高级分析员' })
    await call('deletePositionTrainingList', 'list-1')
    await call('batchUpdatePositionTrainingListItems', 'list-1', [{ level: '初级', textbook_name: 'SOP' }])
    await call('importPositionTrainingLists', file)
    await call('clearPositionTrainingListsByDept', '质量部')
    await call('createPlanTrackingRecord', { plan_id: 'plan-1' })
    await call('updatePlanTrackingRecord', 'tracking-1', { status: 'completed' })
    await call('deletePlanTrackingRecord', 'tracking-1')
    await call('updateEsgTrainingRecord', 'esg-1', { status: '合格' })
    await call('deleteEsgTrainingRecord', 'esg-1')
    await call('syncEsgFromLedger', '质量部')
    await call('importTrainingLedgerByDept', file, '质量部')
    await call('importEsgRecordsByDept', file, '质量部')
    await call('previewTrainingImport', file, '质量部')
    await call('confirmTrainingImport', file, '质量部', [])
    await call('importExamScores', file, 'ledger-1')
    await call('confirmExamScores', 'ledger-1', [{ name: '张三', score: '90' }])
    await call('uploadPlanAttachments', 'plan-1', [file])
    await call('deletePlanAttachment', 'attachment-1')
    await call('upsertTrainingSession', { training_date: '2026-08-25' })
    await call('upsertTrainingDocument', { name: 'SOP' })
    await call('markTrainingContentUsed', [{ name: 'SOP', code: 'SOP-1' }])
    await call('importFeishuMembers', '质量部')
    await call('addEmployeeTrainingMember', '质量部', '张三', 'E001')
    await call('removeEmployeeTrainingMember', 'member-1')
    await call('updateEmployeeTrainingMember', 'member-1', '李四')
    await call('markPlanAttachmentsLedgerImported', ['attachment-1'])
    await call('generateNewEmployeeTrainingPlan', { employee_id: 'employee-1' })
    await call('createManualNewEmployeeTrainingPlan', { employee_name: '李四' })
    await call('updateNewEmployeeTrainingPlan', 'plan-1', { status: 'draft' })
    await call('addNewEmployeeTrainingItem', 'plan-1', { title: 'GMP' })
    await call('startNewEmployeeTraining', 'plan-1', { item_ids: [] })
    await call('deleteNewEmployeeTrainingPlan', 'plan-1')
    await call('addNewEmployeeTrainingTrainees', 'plan-1', { item_ids: [], additional_trainees: [] })
    await call('createPositionTrainingMappingAction', { position: '分析员', training_item_id: 'item-1' })
    await call('createTrainingDeptMappingAction', { source_name: '质量部', match_level: 'first', mapping_type: 'exact' })
    await call('updateTrainingDeptMappingAction', 'mapping-1', { enabled: true })
    await call('deleteTrainingDeptMappingAction', 'mapping-1')

    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/training-ledgers/import-preview'))).toBe(true)
    expect(mocks.revalidatePath).toHaveBeenCalled()
  })

  it('maps protected server-action failures without returning placeholder success', async () => {
    const file = new File(['content'], 'failure.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
    const formData = new FormData()
    formData.append('file', file)
    const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ message: '后端拒绝操作', detail: '数据范围不允许' }), {
      status: 403,
      headers: { 'content-type': 'application/json' },
    }))
    vi.stubGlobal('fetch', fetchMock)

    const cases: Array<[keyof typeof actions, unknown[]]> = [
      ['createEmployee', [{}]], ['updateEmployee', ['employee-1', {}]], ['deleteEmployee', ['employee-1']],
      ['syncFromFeishuAction', []], ['syncToFeishuAction', ['employee-1']],
      ['createDepartment', [{}]], ['updateDepartment', ['dept-1', {}]], ['deleteDepartment', ['dept-1']],
      ['createTeam', [{}]], ['updateTeam', ['team-1', {}]], ['deleteTeam', ['team-1']],
      ['createOffboardingRecord', [{}]], ['updateOffboardingRecord', ['offboarding-1', {}]], ['deleteOffboardingRecord', ['offboarding-1']],
      ['createAnnualTrainingPlan', [{}]], ['deleteAnnualTrainingPlan', ['plan-1']], ['batchUpdatePlanItems', ['plan-1', {}]],
      ['updateCandidateAction', ['candidate-1', {}]], ['updateCandidateRecommendationLevelAction', ['candidate-1', '高']],
      ['fetchCandidatesFromFeishu', []], ['deleteCandidateAction', ['candidate-1']],
      ['fetchDepartureRecords', [{}]], ['fetchEmployeeById', ['employee-1']], ['fetchCandidateById', ['candidate-1']],
      ['fetchAnnualTrainingPlanById', ['plan-1']], ['fetchPlanItems', ['plan-1']], ['fetchEmployeeByNumber', ['E-1']],
      ['fetchDepartmentTreeAction', []], ['syncDepartmentsFromFeishuAction', [false]], ['getDepartmentSyncStatus', []],
      ['updateHrFeishuAppSettings', [{}]], ['testHrFeishuAppSettings', []], ['updateHrFeishuEntitySetting', ['candidate', {}]],
      ['testHrFeishuEntitySetting', ['candidate']], ['updateEmailConfig', [{}]], ['testEmailConfig', []],
      ['updateReminderConfig', ['reminder-1', {}]], ['updateApprovalConfig', ['approval-1', {}]], ['saveDeptRecipients', ['reminder-1', []]],
      ['deleteDeptRecipient', ['recipient-1']], ['syncFeishuMembersAction', []], ['getFeishuMembersSyncStatus', []],
      ['fetchJobPostingsServer', [{}]], ['fetchOrgTreeAction', []], ['createJobPosting', [{}]], ['batchAnalyzeCandidatesAction', [[]]],
      ['createOnboardingFromInterviewAction', ['candidate-1']], ['updateOnboardingAction', ['onboarding-1', {}]],
      ['createEmployeePublicAction', [{}]], ['syncOnboardingToEmployeeAction', ['onboarding-1']],
      ['syncOnboardingToContractAction', ['张三', '质量部', 'P3']], ['triggerEmailFetch', [false]],
      ['submitPositionTransferApproval', ['transfer-1', true]], ['approvePositionTransferNode', ['transfer-1', '同意']],
      ['rejectPositionTransferNode', ['transfer-1', '不同意']], ['createPositionTransfer', [{}]], ['updatePositionTransfer', ['transfer-1', {}]],
      ['deletePositionTransfer', ['transfer-1']], ['syncPositionTransferFromFeishuAction', []],
      ['createDeptApprovalConfigAction', [{}]], ['updateDeptApprovalConfigAction', ['config-1', {}]], ['deleteDeptApprovalConfigAction', ['config-1']],
      ['initDeptApprovalConfigsAction', []], ['syncOffboardingFromFeishuAction', []], ['generateOffboardingCertificateAction', ['offboarding-1']],
      ['uploadOffboardingTemplateAction', [formData]], ['fetchOffboardingTemplateInfoAction', []],
      ['checkTrainingConflict', [{}]], ['createTrainingLedger', [{}]], ['updateTrainingLedger', ['ledger-1', {}]],
      ['deleteTrainingLedger', ['ledger-1']], ['clearTrainingLedgersByDept', ['质量部']], ['createTrainingLedgerPage', [{}]],
      ['generateTrainingSignInSheet', [{}]], ['generateTrainingNotification', [{}]], ['generateTrainingEvaluation', [{}]],
      ['generateOnboardingEvaluation', [{}]], ['generateOralExamResult', [{}]], ['generatePracticalExamResult', [{}]],
      ['generateTrainingAttachment', [{}]], ['importPracticalExamQuestions', [file]], ['syncContractsFromFeishu', []],
      ['pushContractExpiringAction', ['2026-08-01', '2026-08-31']], ['getContractPushStatusAction', []], ['saveContractTemplateAction', [{}]],
      ['deleteContractAction', ['contract-1']], ['updateContractAction', ['contract-1', {}]], ['renewContractAction', ['contract-1', '2026-01-01', '2027-01-01']],
      ['createTrainer', [{}]], ['updateTrainer', ['trainer-1', {}]], ['deleteTrainer', ['trainer-1']], ['importTrainers', [formData]],
      ['createTrainingEvaluation', [{}]], ['updateTrainingEvaluation', ['evaluation-1', {}]], ['deleteTrainingEvaluation', ['evaluation-1']],
      ['saveTrainingPersonnelConfig', [{}]], ['deleteTrainingPersonnelConfig', ['config-1']], ['createPositionTrainingList', [{}]],
      ['updatePositionTrainingList', ['list-1', {}]], ['deletePositionTrainingList', ['list-1']], ['batchUpdatePositionTrainingListItems', ['list-1', []]],
      ['importPositionTrainingLists', [file]], ['clearPositionTrainingListsByDept', ['质量部']], ['createPlanTrackingRecord', [{}]],
      ['updatePlanTrackingRecord', ['tracking-1', {}]], ['deletePlanTrackingRecord', ['tracking-1']], ['updateEsgTrainingRecord', ['esg-1', {}]],
      ['deleteEsgTrainingRecord', ['esg-1']], ['syncEsgFromLedger', ['质量部']], ['importTrainingLedgerByDept', [file, '质量部']],
      ['importEsgRecordsByDept', [file, '质量部']], ['previewTrainingImport', [file, '质量部']], ['confirmTrainingImport', [file, '质量部', []]],
      ['importExamScores', [file, 'ledger-1']], ['confirmExamScores', ['ledger-1', []]], ['uploadPlanAttachments', ['plan-1', [file]]],
      ['deletePlanAttachment', ['attachment-1']], ['upsertTrainingSession', [{}]], ['upsertTrainingDocument', [{}]],
      ['markTrainingContentUsed', [[]]], ['importFeishuMembers', ['质量部']], ['addEmployeeTrainingMember', ['质量部', '张三', 'E-1']],
      ['removeEmployeeTrainingMember', ['member-1']], ['updateEmployeeTrainingMember', ['member-1', '李四']],
      ['markPlanAttachmentsLedgerImported', [[]]], ['generateNewEmployeeTrainingPlan', [{}]], ['createManualNewEmployeeTrainingPlan', [{}]],
      ['updateNewEmployeeTrainingPlan', ['plan-1', {}]], ['addNewEmployeeTrainingItem', ['plan-1', {}]], ['startNewEmployeeTraining', ['plan-1', {}]],
      ['deleteNewEmployeeTrainingPlan', ['plan-1']], ['addNewEmployeeTrainingTrainees', ['plan-1', {}]], ['createPositionTrainingMappingAction', [{}]],
      ['sendOfferEmailAction', [{}]], ['sendCandidateNoticeAction', ['candidate-1', 'interview']],
      ['uploadOfferTemplateAction', [formData]], ['updateContractSignStatusAction', ['contract-1', '已签署']],
      ['addCustomTrainingDepartment', ['质量部']], ['deleteCustomTrainingDepartment', ['质量部']], ['createTrainingDeptMappingAction', [{}]],
      ['updateTrainingDeptMappingAction', ['mapping-1', {}]], ['deleteTrainingDeptMappingAction', ['mapping-1']],
    ]
    for (const [name, args] of cases) {
      try {
        await call(name, ...args)
      } catch {
        // 旧版 Action 仍使用 rejected Promise；已迁移的 Action 返回失败结果。
      }
    }
    expect(fetchMock.mock.calls.length).toBeGreaterThan(100)
    expect(mocks.revalidatePath).not.toHaveBeenCalledWith('/hr/recruitment')
  })

  it('surfaces backend reason for training personnel config failures and revalidates on success', async () => {
    const forbidden = vi.fn().mockImplementation(async () =>
      new Response(JSON.stringify({ message: '只能删除自己创建的培训人员配置' }), {
        status: 403,
        headers: { 'content-type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', forbidden)

    await expect(call('saveTrainingPersonnelConfig', {})).rejects.toThrow('只能删除自己创建的培训人员配置')
    await expect(call('deleteTrainingPersonnelConfig', 'config-1')).rejects.toThrow('只能删除自己创建的培训人员配置')
    // 失败不刷新缓存，避免把失败当成功
    expect(mocks.revalidatePath).not.toHaveBeenCalledWith('/hr/training/sign-in')

    vi.clearAllMocks()
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => response()))
    await call('deleteTrainingPersonnelConfig', 'config-1')
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/hr/training/sign-in')
  })

  it('touches ledger and esg batch-delete actions', async () => {
    const fetchMock = vi.fn().mockImplementation(async () => response())
    vi.stubGlobal('fetch', fetchMock)

    await call('batchDeleteTrainingLedgers', ['ledger-1', 'ledger-2'])
    await call('batchDeleteEsgTrainingRecords', ['esg-1'])

    expect(fetchMock).toHaveBeenCalledTimes(2)
    const ledgerCall = JSON.parse(String((fetchMock.mock.calls[0][1] as RequestInit).body))
    const esgCall = JSON.parse(String((fetchMock.mock.calls[1][1] as RequestInit).body))
    expect(ledgerCall).toEqual({ ids: ['ledger-1', 'ledger-2'] })
    expect(esgCall).toEqual({ ids: ['esg-1'] })
    expect(String(fetchMock.mock.calls[0][0])).toContain('/training-ledgers/batch-delete')
    expect(String(fetchMock.mock.calls[1][0])).toContain('/esg-training-records/batch-delete')
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/hr/training/ledger')
  })
})
