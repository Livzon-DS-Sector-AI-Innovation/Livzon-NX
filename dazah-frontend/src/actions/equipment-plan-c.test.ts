import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ auth: vi.fn(), fetch: vi.fn() }))
vi.mock('@/lib/auth', () => ({ getAuthHeaders: mocks.auth }))
vi.mock('@/lib/server-api', () => ({ getServerApiBaseUrl: () => 'http://backend.test:8000' }))
vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }))

import {
  cancelPurchaseSuggestion,
  deleteLaborRate,
  dismissKnowledgeCase,
  generateMonthlyReport,
  registerSuggestionArrival,
  saveLaborRate,
  submitPurchaseSuggestions,
  transferWorkOrder,
  updateSuggestionQty,
  updateWorkOrderExternalCost,
  verifyKnowledgeCase,
} from './equipment'

beforeEach(() => {
  vi.resetAllMocks()
  mocks.auth.mockResolvedValue({ Authorization: 'Bearer t', 'Content-Type': 'application/json' })
  mocks.fetch.mockImplementation(async () =>
    new Response(JSON.stringify({ code: 200, data: { id: 'x' } }), { status: 200 }),
  )
  vi.stubGlobal('fetch', mocks.fetch)
})
afterEach(() => vi.unstubAllGlobals())

describe('设备模块方案B/C/E Server Actions', () => {
  it('携带认证头调用后端', async () => {
    await transferWorkOrder('wo-1', { assignee_id: 'u-1' })
    const init = mocks.fetch.mock.calls.at(-1)![1] as RequestInit
    const headers = init.headers as Record<string, string>
    expect(headers.Authorization).toBe('Bearer t')
  })

  it('transferWorkOrder 调 PUT /transfer 并回填 body', async () => {
    await transferWorkOrder('wo-1', { assignee_id: 'u-1', reason: '不在厂' })
    const [url, init] = mocks.fetch.mock.calls.at(-1)!
    expect(String(url)).toContain('/api/v1/equipment/maintenance/work-orders/wo-1/transfer')
    expect(init?.method).toBe('PUT')
    expect(JSON.parse(String(init?.body))).toEqual({ assignee_id: 'u-1', reason: '不在厂' })
  })

  it('generateMonthlyReport 调 POST 月报生成', async () => {
    await generateMonthlyReport('2026-10')
    const [url, init] = mocks.fetch.mock.calls.at(-1)!
    expect(String(url)).toContain('/health/monthly-reports/generate')
    expect(init?.method).toBe('POST')
    expect(JSON.parse(String(init?.body))).toEqual({ report_month: '2026-10' })
  })

  it('知识案例确认/忽略走 POST', async () => {
    await verifyKnowledgeCase('c1')
    expect(String(mocks.fetch.mock.calls.at(-1)![0])).toContain('/repair-knowledge/cases/c1/verify')
    await dismissKnowledgeCase('c2')
    expect(String(mocks.fetch.mock.calls.at(-1)![0])).toContain('/cases/c2/dismiss')
    expect(mocks.fetch.mock.calls.at(-1)![1]?.method).toBe('POST')
  })

  it('采购建议批量提交传 ID 列表', async () => {
    await submitPurchaseSuggestions(['s1', 's2'])
    const [url, init] = mocks.fetch.mock.calls.at(-1)!
    expect(String(url)).toContain('/spare-parts/purchase-suggestions/submit')
    expect(JSON.parse(String(init?.body))).toEqual({ suggestion_ids: ['s1', 's2'] })
  })

  it('采购建议调量/到货/取消走对应方法', async () => {
    await updateSuggestionQty('s1', 12)
    let [url, init] = mocks.fetch.mock.calls.at(-1)!
    expect(String(url)).toContain('/purchase-suggestions/s1/qty')
    expect(init?.method).toBe('PUT')

    await registerSuggestionArrival('s1', 5)
    ;[url, init] = mocks.fetch.mock.calls.at(-1)!
    expect(String(url)).toContain('/s1/arrival')
    expect(init?.method).toBe('POST')

    await cancelPurchaseSuggestion('s1')
    ;[url, init] = mocks.fetch.mock.calls.at(-1)!
    expect(String(url)).toContain('/s1/cancel')
    expect(init?.method).toBe('POST')
  })

  it('费率新增/删除', async () => {
    await saveLaborRate({ scope: 'person', person_id: 'u1', hourly_rate: 60 })
    expect(String(mocks.fetch.mock.calls.at(-1)![0])).toContain('/labor-rates')
    expect(mocks.fetch.mock.calls.at(-1)![1]?.method).toBe('POST')

    await deleteLaborRate('r1')
    expect(String(mocks.fetch.mock.calls.at(-1)![0])).toContain('/labor-rates/r1')
    expect(mocks.fetch.mock.calls.at(-1)![1]?.method).toBe('DELETE')
  })

  it('外委费用补录 PUT', async () => {
    await updateWorkOrderExternalCost('wo-9', { external_cost: 200, external_vendor: '厂' })
    const [url, init] = mocks.fetch.mock.calls.at(-1)!
    expect(String(url)).toContain('/wo-9/external-cost')
    expect(JSON.parse(String(init?.body))).toEqual({ external_cost: 200, external_vendor: '厂' })
  })

  it('后端错误转换为业务异常消息', async () => {
    mocks.fetch.mockResolvedValueOnce(
      new Response(JSON.stringify({ code: 400, message: '状态不允许转派' }), { status: 400 }),
    )
    await expect(transferWorkOrder('wo-1', { assignee_id: 'u-2' })).rejects.toThrow('状态不允许转派')
  })
})
