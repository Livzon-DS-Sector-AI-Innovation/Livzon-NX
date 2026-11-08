import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getAuthHeaders: vi.fn().mockResolvedValue({
    Authorization: 'Bearer test-token',
    'Content-Type': 'application/json',
  }),
  revalidatePath: vi.fn(),
}))

vi.mock('@/lib/auth', () => ({ getAuthHeaders: mocks.getAuthHeaders }))
vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidatePath }))

import * as safety from './safety'
import {
  WORK_CERTIFICATES_PAGE_KEY,
  WORK_PERMITS_PAGE_KEY,
  certificateFileContentUrl,
  certificateFilePreviewUrl,
} from '@/lib/work-permit-api'

const PERMIT_PAGE_KEY = 'safety:ops-safety:work-permits'
const CERT_PAGE_KEY = 'safety:ops-safety:work-certificates'

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

afterEach(() => {
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

describe('8 大作业票 actions', () => {
  it('列表：查询参数与页面键', async () => {
    const [url, init] = await capture(() =>
      safety.getWorkPermits({
        page: 2,
        pageSize: 10,
        permitType: 'hot_work',
        status: 'pending_approval',
        keyword: '动火',
      }),
    )
    expect(url).toContain('/api/v1/safety/work-permits?')
    expect(url).toContain('page=2')
    expect(url).toContain('page_size=10')
    expect(url).toContain('permit_type=hot_work')
    expect(url).toContain('status=pending_approval')
    expect((init?.headers as Record<string, string>)['X-Dazah-Page-Key']).toBe(
      PERMIT_PAGE_KEY,
    )
  })

  it('详情：路径参数', async () => {
    const [url] = await capture(() => safety.getWorkPermitDetail('p1'))
    expect(url).toContain('/api/v1/safety/work-permits/p1')
  })

  it('运行参数：读取与保存证件强校验开关', async () => {
    const [getUrl, getInit] = await capture(() => safety.getWorkPermitSettings())
    expect(getUrl).toContain('/api/v1/safety/work-permit-settings')
    expect(
      (getInit?.headers as Record<string, string>)['X-Dazah-Page-Key'],
    ).toBe(PERMIT_PAGE_KEY)

    const [putUrl, putInit] = await capture(() =>
      safety.updateWorkPermitSettings(true),
    )
    expect(putUrl).toContain('/api/v1/safety/work-permit-settings')
    expect(String(putInit?.method)).toBe('PUT')
    expect(putInit?.body).toBe(JSON.stringify({ cert_check_strict: true }))
  })

  it('提交审批：携带节点指派', async () => {
    const [url, init] = await capture(() =>
      safety.submitWorkPermit('p1', [
        { node_key: 'safety_officer', approver_user_id: 'u1' },
        { node_key: 'workshop_leader', approver_user_id: null },
      ]),
    )
    expect(url).toContain('/api/v1/safety/work-permits/p1/submit')
    const body = JSON.parse(String(init?.body))
    expect(body.assignments).toHaveLength(2)
    expect(body.assignments[0]).toEqual({
      node_key: 'safety_officer',
      approver_user_id: 'u1',
    })
  })

  it('签批/驳回：节点路径与请求体', async () => {
    const [approveUrl, approveInit] = await capture(() =>
      safety.approveWorkPermitNode('p1', 'n1', '同意'),
    )
    expect(approveUrl).toContain('/api/v1/safety/work-permits/p1/nodes/n1/approve')
    expect(JSON.parse(String(approveInit?.body))).toEqual({ opinion: '同意' })

    const [rejectUrl, rejectInit] = await capture(() =>
      safety.rejectWorkPermitNode('p1', 'n1', '材料不全'),
    )
    expect(rejectUrl).toContain('/api/v1/safety/work-permits/p1/nodes/n1/reject')
    expect(JSON.parse(String(rejectInit?.body))).toEqual({ opinion: '材料不全' })
  })

  it('验票与完工验收', async () => {
    const [verifyUrl] = await capture(() => safety.verifyWorkPermit('p1'))
    expect(verifyUrl).toContain('/api/v1/safety/work-permits/p1/verify')

    const [acceptUrl, acceptInit] = await capture(() =>
      safety.acceptWorkPermit('p1', { dismantle_person: '张三' }),
    )
    expect(acceptUrl).toContain('/api/v1/safety/work-permits/p1/accept')
    expect(JSON.parse(String(acceptInit?.body)).type_data).toEqual({
      dismantle_person: '张三',
    })
  })

  it('气体分析与关联票', async () => {
    const [gasUrl, gasInit] = await capture(() =>
      safety.addWorkPermitGasAnalysis('p1', {
        phase: 'on_duty',
        sampled_at: '2026-11-06T10:00:00+08:00',
        items: [{ name: '可燃气体', standard: '0', value: '0' }],
      }),
    )
    expect(gasUrl).toContain('/api/v1/safety/work-permits/p1/gas-analyses')
    expect(JSON.parse(String(gasInit?.body)).phase).toBe('on_duty')

    const [relUrl, relInit] = await capture(() =>
      safety.addWorkPermitRelation('p1', 'p2'),
    )
    expect(relUrl).toContain('/api/v1/safety/work-permits/p1/relations')
    expect(JSON.parse(String(relInit?.body)).related_permit_id).toBe('p2')
  })

  it('操作成功后失效列表缓存', async () => {
    vi.stubGlobal('fetch', vi.fn(() => jsonResponse({ code: 200, data: null })))
    await safety.createWorkPermit({
      permit_type: 'blind_plate',
      permit_level: 'none',
    })
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/safety/work-permits')
  })
})

describe('特种作业证件 actions', () => {
  it('列表：筛选参数与页面键', async () => {
    const [url, init] = await capture(() =>
      safety.getWorkCertificates({
        page: 1,
        pageSize: 20,
        certificateCategory: 'electrician',
        status: 'expiring',
        keyword: '王',
        expiringDays: 30,
      }),
    )
    expect(url).toContain('/api/v1/safety/work-certificates?')
    expect(url).toContain('certificate_category=electrician')
    expect(url).toContain('status=expiring')
    expect(url).toContain('expiring_days=30')
    expect((init?.headers as Record<string, string>)['X-Dazah-Page-Key']).toBe(
      CERT_PAGE_KEY,
    )
  })

  it('创建/更新/删除走对应方法', async () => {
    const [createUrl, createInit] = await capture(() =>
      safety.createWorkCertificate({ person_name: '王五', certificate_category: 'electrician' }),
    )
    expect(createUrl).toContain('/api/v1/safety/work-certificates')
    expect(String(createInit?.method)).toBe('POST')

    const [updateUrl, updateInit] = await capture(() =>
      safety.updateWorkCertificate('c1', { certificate_no: 'T2' }),
    )
    expect(updateUrl).toContain('/api/v1/safety/work-certificates/c1')
    expect(String(updateInit?.method)).toBe('PUT')

    const [deleteUrl] = await capture(() => safety.deleteWorkCertificate('c1'))
    expect(deleteUrl).toContain('/api/v1/safety/work-certificates/c1')
  })

  it('附件 URL 生成', () => {
    expect(certificateFileContentUrl('c1', 'f1')).toBe(
      '/api/v1/safety/work-certificates/c1/files/f1/content',
    )
    expect(certificateFilePreviewUrl('c1', 'f1')).toBe(
      '/api/v1/safety/work-certificates/c1/files/f1/preview',
    )
  })

  it('Excel 导入：multipart 直传、去 JSON Content-Type、勾选子表', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: null }))
    vi.stubGlobal('fetch', fetchMock)
    const file = new File(['x'], 'ledger.xlsx', {
      type: 'application/octet-stream',
    })

    await safety.parseCertificateImport(file)
    const [parseUrl, parseInit] = fetchMock.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ]
    expect(parseUrl).toContain(
      '/api/v1/safety/work-certificates/import/parse',
    )
    expect(parseInit?.body).toBeInstanceOf(FormData)
    expect(
      (parseInit?.headers as Record<string, string>)['Content-Type'],
    ).toBeUndefined()
    expect(
      (parseInit?.headers as Record<string, string>)['X-Dazah-Page-Key'],
    ).toBe(CERT_PAGE_KEY)

    await safety.importCertificates(file, ['电焊', '电工（高）'])
    const [importUrl, importInit] = fetchMock.mock.calls[1] as unknown as [
      string,
      RequestInit,
    ]
    expect(importUrl).toContain('/api/v1/safety/work-certificates/import')
    expect(importUrl).not.toContain('/import/parse')
    const formData = importInit?.body as FormData
    expect(formData.get('sheets')).toBe(JSON.stringify(['电焊', '电工（高）']))
    expect(mocks.revalidatePath).toHaveBeenCalledWith(
      '/safety/work-certificates',
    )
  })
})
