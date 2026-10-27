import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getAuthHeaders: vi
    .fn()
    .mockResolvedValue({ Authorization: 'Bearer test-token' }),
  revalidatePath: vi.fn(),
}))

vi.mock('@/lib/auth', () => ({ getAuthHeaders: mocks.getAuthHeaders }))
vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidatePath }))

import * as safety from './safety'

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json' },
    }),
  )
}

async function capture(
  fn: () => Promise<unknown>,
): Promise<[string, RequestInit | undefined]> {
  const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: null }))
  vi.stubGlobal('fetch', fetchMock)
  await fn()
  const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
  return [url, init]
}

beforeEach(() => {
  // 下载类 action 会创建 <a> 触发浏览器下载，node 环境补最小桩
  vi.stubGlobal('document', {
    createElement: () => ({ click: () => {}, href: '', download: '' }),
    body: { appendChild: () => {}, removeChild: () => {} },
  })
  vi.stubGlobal('URL', { ...URL, createObjectURL: () => 'blob:x', revokeObjectURL: () => {} })
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

describe('safety governance actions（批次4：法规/处置卡/目标/设施/危化/应急）', () => {
  it('法规：批量上传与合规评审', async () => {
    const [u1] = await capture(() =>
      safety.batchUploadRegulations([new File(['x'], 'a.pdf')]),
    )
    expect(u1).toContain('/api/v1/safety/regulations/batch-upload')

    const [u2, i2] = await capture(() => safety.runComplianceReview('r1'))
    expect(u2).toContain('/api/v1/safety/regulations/r1/compliance-review')
    expect(i2?.method).toBe('POST')

    const [u3] = await capture(() => safety.getRegulationReviews('r1'))
    expect(u3).toContain('/api/v1/safety/regulations/r1/reviews')

    const [u4] = await capture(() => safety.getLatestRegulationReviews(['r1', 'r2']))
    expect(u4).toContain('/api/v1/safety/regulation-reviews/latest')

    const [u5] = await capture(() => safety.getRegulationDocumentPreview('r1'))
    expect(u5).toContain('/api/v1/safety/regulations/r1/document-content')

    const [u6] = await capture(() => safety.downloadRegulationDocument('r1'))
    expect(u6).toContain('/api/v1/safety/regulations/r1/document')
  })

  it('应急处置卡：列表/统计/详情/增改删/AI 评审', async () => {
    const [u1] = await capture(() =>
      safety.getEmergencyCards({ page: 1, page_size: 10, workshop: '101' }),
    )
    expect(u1).toContain('/api/v1/safety/emergency-cards')

    const [u2] = await capture(() => safety.getEmergencyCardStats())
    expect(u2).toContain('/api/v1/safety/emergency-cards/stats')

    const [u3] = await capture(() => safety.getEmergencyCard('e1'))
    expect(u3).toContain('/api/v1/safety/emergency-cards/e1')

    const [u4, i4] = await capture(() =>
      safety.createEmergencyCard({
        title: 't',
        workshop: '101',
        scene: 's',
        risk: 'r',
        steps: [],
      } as never),
    )
    expect(u4).toContain('/api/v1/safety/emergency-cards')
    expect(i4?.method).toBe('POST')

    const [u5, i5] = await capture(() =>
      safety.updateEmergencyCard('e1', { title: 't2' } as never),
    )
    expect(u5).toContain('/api/v1/safety/emergency-cards/e1')
    expect(i5?.method).toBe('PUT')

    const [, i6] = await capture(() => safety.deleteEmergencyCard('e1'))
    expect(i6?.method).toBe('DELETE')

    const [u7, i7] = await capture(() => safety.reviewEmergencyCard('e1'))
    expect(u7).toContain('/api/v1/safety/emergency-cards/e1/ai-review')
    expect(i7?.method).toBe('POST')
  })

  it('安全总览与目标绩效', async () => {
    const [u1] = await capture(() => safety.getSafetyOverview())
    expect(u1).toContain('/api/v1/safety/dashboard/overview')

    const [u2] = await capture(() => safety.getFireEquipmentDashboard({ pageKey: 'k' }))
    expect(u2).toContain('/api/v1/safety/fire-equipment/dashboard')

    const [u3] = await capture(() => safety.getSafetyTargets({ year: 2026 }))
    expect(u3).toContain('/api/v1/safety/safety-targets')

    const [u4] = await capture(() => safety.getSafetyTargetStats(2026))
    expect(u4).toContain('/api/v1/safety/safety-targets/stats')

    const [u5] = await capture(() => safety.getSafetyTarget('t1'))
    expect(u5).toContain('/api/v1/safety/safety-targets/t1')

    const [, i6] = await capture(() =>
      safety.createSafetyTarget({ year: 2026 } as never),
    )
    expect(i6?.method).toBe('POST')

    const [, i7] = await capture(() =>
      safety.updateSafetyTarget('t1', { year: 2026 } as never),
    )
    expect(i7?.method).toBe('PUT')

    const [, i8] = await capture(() => safety.deleteSafetyTarget('t1'))
    expect(i8?.method).toBe('DELETE')

    const [u9, i9] = await capture(() =>
      safety.upsertSafetyTargetRecord('t1', '2026-Q1', { value: 1 } as never),
    )
    expect(u9).toContain('/api/v1/safety/safety-targets/t1/records/2026-Q1')
    expect(i9?.method).toBe('PUT')

    const [, i10] = await capture(() =>
      safety.deleteSafetyTargetRecord('t1', '2026-Q1'),
    )
    expect(i10?.method).toBe('DELETE')
  })

  it('安全设施：清单/统计/检查卡/增改删/巡检提交', async () => {
    const [u1] = await capture(() =>
      safety.getSafetyFacilities({ category: '消防设施' }),
    )
    expect(u1).toContain('/api/v1/safety/safety-facilities')

    const [u2] = await capture(() => safety.getSafetyFacilityStats())
    expect(u2).toContain('/api/v1/safety/safety-facilities/stats')

    const [u3] = await capture(() =>
      safety.getSafetyFacilityChecklist('消防设施'),
    )
    expect(u3).toContain('/api/v1/safety/safety-facilities/checklist')

    const [u4] = await capture(() => safety.getSafetyFacility('f1'))
    expect(u4).toContain('/api/v1/safety/safety-facilities/f1')

    const [, i5] = await capture(() =>
      safety.createSafetyFacility({ name: 'n' } as never),
    )
    expect(i5?.method).toBe('POST')

    const [, i6] = await capture(() =>
      safety.updateSafetyFacility('f1', { name: 'n' } as never),
    )
    expect(i6?.method).toBe('PUT')

    const [, i7] = await capture(() => safety.deleteSafetyFacility('f1'))
    expect(i7?.method).toBe('DELETE')

    const [u8, i8] = await capture(() =>
      safety.submitSafetyFacilityInspection('f1', { items: [] } as never),
    )
    expect(u8).toContain('/api/v1/safety/safety-facilities/f1/inspections')
    expect(i8?.method).toBe('POST')
  })

  it('危化品：档案/库存/超储/MSDS 上传', async () => {
    const [u1] = await capture(() => safety.getHazardousChemicals({ page: 1 }))
    expect(u1).toContain('/api/v1/safety/hazardous-chemicals')

    const [u2] = await capture(() => safety.getHazchemStats())
    expect(u2).toContain('/api/v1/safety/hazardous-chemicals/stats')

    const [u3] = await capture(() => safety.getOverLimitChemicals(5))
    expect(u3).toContain('/api/v1/safety/hazardous-chemicals/over-limit')

    const [u4] = await capture(() => safety.getChemicalInventories({}))
    expect(u4).toContain('/api/v1/safety/chemical-inventories')

    const [, i5] = await capture(() =>
      safety.createHazardousChemical({ name: 'n' } as never),
    )
    expect(i5?.method).toBe('POST')

    const [, i6] = await capture(() =>
      safety.updateHazardousChemical('c1', { name: 'n' } as never),
    )
    expect(i6?.method).toBe('PUT')

    const [, i7] = await capture(() => safety.deleteHazardousChemical('c1'))
    expect(i7?.method).toBe('DELETE')

    const [u8, i8] = await capture(() =>
      safety.uploadChemicalMsds('c1', new File(['x'], 'msds.pdf')),
    )
    expect(u8).toContain('/api/v1/safety/')
    expect(i8?.method).toBe('POST')

    const [, i9] = await capture(() =>
      safety.createChemicalInventory({ chemical_id: 'c1' } as never),
    )
    expect(i9?.method).toBe('POST')

    const [, i10] = await capture(() =>
      safety.updateChemicalInventory('i1', { quantity: 1 } as never),
    )
    expect(i10?.method).toBe('PUT')

    const [, i11] = await capture(() => safety.deleteChemicalInventory('i1'))
    expect(i11?.method).toBe('DELETE')
  })

  it('应急管理：预案/演练/物资/统计/附件', async () => {
    const [u1] = await capture(() => safety.getEmergencyPlans({}))
    expect(u1).toContain('/api/v1/safety/emergency-plans')

    const [u2] = await capture(() => safety.getEmergencyMgmtStats())
    expect(u2).toContain('/api/v1/safety/emergency-mgmt/stats')

    const [, i3] = await capture(() =>
      safety.createEmergencyPlan({ name: 'n' } as never),
    )
    expect(i3?.method).toBe('POST')

    const [, i4] = await capture(() =>
      safety.updateEmergencyPlan('p1', { name: 'n' } as never),
    )
    expect(i4?.method).toBe('PUT')

    const [, i5] = await capture(() => safety.deleteEmergencyPlan('p1'))
    expect(i5?.method).toBe('DELETE')

    const [, i6] = await capture(() =>
      safety.uploadEmergencyPlanFile('p1', new File(['x'], 'plan.pdf')),
    )
    expect(i6?.method).toBe('POST')

    const [u7] = await capture(() =>
      safety.downloadEmergencyPlanFile('p1'),
    )
    expect(u7).toContain('/api/v1/safety/')

    const [u8] = await capture(() => safety.getEmergencyDrills({}))
    expect(u8).toContain('/api/v1/safety/emergency-drills')

    const [, i9] = await capture(() =>
      safety.createEmergencyDrill({ title: 't' } as never),
    )
    expect(i9?.method).toBe('POST')

    const [, i10] = await capture(() =>
      safety.updateEmergencyDrill('d1', { title: 't' } as never),
    )
    expect(i10?.method).toBe('PUT')

    const [, i11] = await capture(() => safety.deleteEmergencyDrill('d1'))
    expect(i11?.method).toBe('DELETE')

    const [u12] = await capture(() => safety.getEmergencySupplies({}))
    expect(u12).toContain('/api/v1/safety/emergency-supplies')

    const [, i13] = await capture(() =>
      safety.createEmergencySupply({ name: 'n' } as never),
    )
    expect(i13?.method).toBe('POST')

    const [, i14] = await capture(() =>
      safety.updateEmergencySupply('s1', { name: 'n' } as never),
    )
    expect(i14?.method).toBe('PUT')

    const [, i15] = await capture(() => safety.deleteEmergencySupply('s1'))
    expect(i15?.method).toBe('DELETE')
  })

  it('列表查询的完整参数分支（page_size 与过滤维度）', async () => {
    const calls: Array<() => Promise<unknown>> = [
      () => safety.getEmergencyCards({ page: 2, page_size: 5, workshop: '101一车间', position: '投料', accident_type: '火灾', keyword: 'k' }),
      () => safety.getSafetyTargets({ page: 2, page_size: 5, year: 2026, category: '安全', status: 'active' }),
      () => safety.getSafetyFacilities({ page: 2, page_size: 5, category: '消防', department: '101', status: 'normal' }),
      () => safety.getHazardousChemicals({ page: 2, page_size: 5, keyword: '乙醇', category: '易燃' }),
      () => safety.getChemicalInventories({ page: 2, page_size: 5, workshop: '101', over_limit_only: true }),
      () => safety.getEmergencyPlans({ page: 2, page_size: 5, plan_type: 'onsite', status: 'active', keyword: '消防' }),
      () => safety.getEmergencyDrills({ page: 2, page_size: 5, year: 2026, keyword: '演练' }),
      () => safety.getEmergencySupplies({ page: 2, page_size: 5, category: '救援', keyword: '担架' }),
    ]
    for (const call of calls) {
      await capture(call)
    }
  })

  it('上传/下载的非 JSON 错误分支（text 响应）', async () => {
    const textResponse = () =>
      Promise.resolve(new Response('后端网关错误', { status: 502, headers: { 'Content-Type': 'text/plain' } }))
    vi.stubGlobal('fetch', vi.fn(textResponse))
    const results = await Promise.allSettled([
      safety.batchUploadRegulations([new File(['x'], 'a.pdf')]),
      safety.uploadChemicalMsds('c1', new File(['x'], 'm.pdf')),
      safety.uploadEmergencyPlanFile('p1', new File(['x'], 'p.pdf')),
    ])
    for (const r of results) {
      expect(r.status).toBe('fulfilled')
    }
    // 下载类把非 2xx 当错误抛出
    await expect(safety.downloadRegulationDocument('r1')).rejects.toThrow()
    await expect(safety.downloadEmergencyPlanFile('p1')).rejects.toThrow()
    vi.unstubAllGlobals()
  })

  it('设施巡检记录查询与 MSDS 下载成功路径', async () => {
    const [u1] = await capture(() =>
      safety.getSafetyFacilityInspections({ page: 1, page_size: 5, facility_id: 'f1', result: 'ok' }),
    )
    expect(u1).toContain('/api/v1/safety/safety-facility-inspections')

    // MSDS 下载成功：返回二进制并触发 a.click
    const blobResponse = () =>
      Promise.resolve(new Response(new Blob(['pdf']), { status: 200 }))
    vi.stubGlobal('fetch', vi.fn(blobResponse))
    await safety.downloadChemicalMsds('c1')
    vi.unstubAllGlobals()
  })
})
