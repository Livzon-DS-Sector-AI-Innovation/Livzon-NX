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

const PAGE_KEY = 'safety:safety-commitment'

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
  body: unknown = { code: 200, data: null },
): Promise<[string, RequestInit | undefined]> {
  const fetchMock = vi.fn(() => jsonResponse(body))
  vi.stubGlobal('fetch', fetchMock)
  await fn()
  const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
  return [url, init]
}

function headerOf(init: RequestInit | undefined, name: string) {
  return (init?.headers as Record<string, string> | undefined)?.[name]
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

describe('安全承诺 actions', () => {
  it('当日日报：GET today + 页面键', async () => {
    const [url, init] = await capture(() => safety.getCommitmentToday())
    expect(url).toContain('/api/v1/safety/safety-commitments/today')
    expect(headerOf(init, 'X-Dazah-Page-Key')).toBe(PAGE_KEY)
  })

  it('按日期查看：GET by-date', async () => {
    const [url] = await capture(() => safety.getCommitmentByDate('2026-11-08'))
    expect(url).toContain('/api/v1/safety/safety-commitments/by-date/2026-11-08')
  })

  it('编辑日报：PUT + JSON 体 + 成功后刷新页面', async () => {
    const [url, init] = await capture(
      () =>
        safety.updateCommitment('r-1', {
          enterprise_status: { workshop_total: 6 },
          commitment_text: '承诺',
        }),
      { code: 200, data: { report: { id: 'r-1' } } },
    )
    expect(url).toContain('/api/v1/safety/safety-commitments/r-1')
    expect(init?.method).toBe('PUT')
    expect(JSON.parse(String(init?.body))).toEqual({
      enterprise_status: { workshop_total: 6 },
      commitment_text: '承诺',
    })
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/safety/safety-commitment')
  })

  it('发布承诺：POST publish + 承诺人', async () => {
    const [url, init] = await capture(
      () => safety.publishCommitment('r-1', '秦刚'),
      { code: 200, data: { report: { id: 'r-1' } } },
    )
    expect(url).toContain('/api/v1/safety/safety-commitments/r-1/publish')
    expect(init?.method).toBe('POST')
    expect(JSON.parse(String(init?.body))).toEqual({ publisher_name: '秦刚' })
  })

  it('AI 研判：POST risk-assessment', async () => {
    const [url, init] = await capture(() =>
      safety.regenerateCommitmentRiskAssessment('r-1'),
    )
    expect(url).toContain('/api/v1/safety/safety-commitments/r-1/risk-assessment')
    expect(init?.method).toBe('POST')
  })

  it('信息卡：列表按类型过滤、新增/编辑/删除', async () => {
    const [listUrl] = await capture(() => safety.getCommitmentCards('major_hazard'))
    expect(listUrl).toContain('/api/v1/safety/safety-commitment-cards?card_type=major_hazard')

    const [createUrl, createInit] = await capture(() =>
      safety.createCommitmentCard({
        card_type: 'commitment',
        title: '标题',
        content: '内容',
      }),
    )
    expect(createUrl).toContain('/api/v1/safety/safety-commitment-cards')
    expect(createInit?.method).toBe('POST')

    const [updateUrl, updateInit] = await capture(() =>
      safety.updateCommitmentCard('c-1', { content: '新内容' }),
    )
    expect(updateUrl).toContain('/api/v1/safety/safety-commitment-cards/c-1')
    expect(updateInit?.method).toBe('PUT')

    const [deleteUrl, deleteInit] = await capture(() =>
      safety.deleteCommitmentCard('c-1'),
    )
    expect(deleteUrl).toContain('/api/v1/safety/safety-commitment-cards/c-1')
    expect(deleteInit?.method).toBe('DELETE')
  })

  it('填报推送测试：POST 设置页测试端点 + 飞书设置页键', async () => {
    const [url, init] = await capture(() => safety.testCommitmentNotify())
    expect(url).toContain('/api/v1/safety/feishu-settings/commitment-notify/test')
    expect(init?.method).toBe('POST')
    expect(headerOf(init, 'X-Dazah-Page-Key')).toBe(
      'safety:system-config:safety-feishu-settings',
    )
  })

  it('写失败时不刷新页面', async () => {
    await capture(
      () => safety.updateCommitment('r-1', { commitment_text: 'x' }),
      { code: 500, message: '失败' },
    )
    expect(mocks.revalidatePath).not.toHaveBeenCalled()
  })
})
