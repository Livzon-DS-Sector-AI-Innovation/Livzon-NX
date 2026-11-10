/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getCommitmentToday: vi.fn(),
  getCommitmentByDate: vi.fn(),
  getCommitmentCards: vi.fn(),
  updateCommitment: vi.fn(),
  publishCommitment: vi.fn(),
  regenerateCommitmentRiskAssessment: vi.fn(),
  createCommitmentCard: vi.fn(),
  updateCommitmentCard: vi.fn(),
  deleteCommitmentCard: vi.fn(),
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  canOperate: true,
  canAccess: true,
}))

vi.mock('@/actions/safety', () => ({
  getCommitmentToday: mocks.getCommitmentToday,
  getCommitmentByDate: mocks.getCommitmentByDate,
  getCommitmentCards: mocks.getCommitmentCards,
  updateCommitment: mocks.updateCommitment,
  publishCommitment: mocks.publishCommitment,
  regenerateCommitmentRiskAssessment: mocks.regenerateCommitmentRiskAssessment,
  createCommitmentCard: mocks.createCommitmentCard,
  updateCommitmentCard: mocks.updateCommitmentCard,
  deleteCommitmentCard: mocks.deleteCommitmentCard,
}))

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>()
  return {
    ...actual,
    message: mocks.message,
    App: { ...actual.App, useApp: () => ({ message: mocks.message }) },
  }
})

vi.mock('@/hooks/usePagePermissions', () => ({
  usePagePermissions: () => ({
    canAccess: mocks.canAccess,
    canQuery: mocks.canAccess,
    canOperate: mocks.canOperate,
    canDelete: mocks.canOperate,
    canExport: false,
    canImport: false,
    canSync: false,
    canApprove: false,
    canReject: false,
  }),
}))

// happy-dom 解析 antd SVG 会截断 DOM：统一把图标替换为空占位
vi.mock('@ant-design/icons', () => {
  const Icon = () => null
  return {
    DeleteOutlined: Icon,
    EditOutlined: Icon,
    PlusOutlined: Icon,
    ReloadOutlined: Icon,
    SendOutlined: Icon,
  }
})

import { SafetyCommitmentPanel } from './SafetyCommitmentPanel'
import { todayStr } from '@/lib/safety-commitment'

const REPORT = {
  id: 'r-1',
  // 与面板 isToday 判断同一口径（北京时间），避免 UTC CI 主机上日期错位
  report_date: todayStr(),
  enterprise_status: {
    workshop_total: 6,
    workshop_running: 5,
    hazard_count: 2,
    person_main: '秦刚',
    special_work: { hot_work_level1: 1, other: 0 },
    hazard_rectified: true,
  },
  commitment_text: '今日郑重承诺。',
  risk_assessment: {
    risk_level: '中',
    summary: '当日有一处动火作业。',
    key_risks: ['动火作业'],
    suggestions: ['配置监火人'],
    generated_at: '2026-11-09T08:00:00+00:00',
  },
  status: 'draft',
  publisher_name: null,
  published_at: null,
  fill_source: 'web',
}

const CARDS = [
  {
    id: 'c-1',
    card_type: 'commitment',
    title: '承诺公告制度',
    content: '每日上午10时更新公告。',
    sort_order: 0,
  },
  {
    id: 'c-2',
    card_type: 'major_hazard',
    title: '储罐区管控要点',
    content: '液位温度压力不超限。',
    sort_order: 0,
  },
]

function flush(ms = 60) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function buttons(text: string) {
  // antd 两个汉字按钮会在中间插入空格（如「编 辑」），统一去掉空白再匹配
  return Array.from(
    document.body.querySelectorAll<HTMLButtonElement>('button'),
  ).filter((b) => b.textContent?.replace(/\s/g, '').includes(text))
}

let root: Root | null = null
let container: HTMLDivElement | null = null

async function renderPanel(props?: Partial<Record<string, unknown>>) {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  await act(async () => {
    root!.render(
      <SafetyCommitmentPanel
        initialReport={REPORT as never}
        initialCreatedToday={false}
        initialCards={CARDS as never}
        initialError={null}
        {...props}
      />,
    )
  })
  await flush()
}

beforeEach(() => {
  mocks.getCommitmentToday.mockResolvedValue({
    code: 200,
    data: { report: REPORT, created_today: false },
  })
  mocks.getCommitmentCards.mockResolvedValue({
    code: 200,
    data: { cards: CARDS },
  })
  mocks.updateCommitment.mockResolvedValue({
    code: 200,
    data: { report: REPORT },
  })
})

afterEach(() => {
  act(() => {
    root?.unmount()
  })
  container?.remove()
  root = null
  container = null
  vi.clearAllMocks()
})

describe('SafetyCommitmentPanel', () => {
  it('渲染企业状态数值、滚动信息卡与 AI 研判', async () => {
    await renderPanel()
    const text = document.body.textContent ?? ''
    expect(text).toContain('企业状态')
    expect(text).toContain('安全承诺信息')
    expect(text).toContain('重大危险源信息')
    expect(text).toContain('承诺公告制度')
    expect(text).toContain('储罐区管控要点')
    expect(text).toContain('安全风险研判')
    expect(text).toContain('当日有一处动火作业')
    expect(text).toContain('企业安全承诺')
    expect(text).toContain('秦刚')
    // 轮播容器可横向滚动
    const carousel = document.querySelector(
      '[data-testid="commitment-carousel-commitment"]',
    ) as HTMLElement | null
    expect(carousel).not.toBeNull()
    expect(carousel!.style.overflowX).toBe('auto')
  })

  it('编辑企业状态并保存', async () => {
    await renderPanel()
    act(() => {
      buttons('编辑')[0]?.click()
    })
    await flush()
    act(() => {
      buttons('保存')[0]?.click()
    })
    await flush()
    expect(mocks.updateCommitment).toHaveBeenCalledWith(
      'r-1',
      expect.objectContaining({ enterprise_status: expect.any(Object) }),
      'safety:safety-commitment',
    )
    expect(mocks.message.success).toHaveBeenCalledWith('企业状态已保存')
  })

  it('AI 风险研判按钮触发重新生成', async () => {
    mocks.regenerateCommitmentRiskAssessment.mockResolvedValue({
      code: 200,
      data: { success: true, report: REPORT },
    })
    await renderPanel()
    act(() => {
      buttons('重新AI研判')[0]?.click()
    })
    await flush()
    expect(mocks.regenerateCommitmentRiskAssessment).toHaveBeenCalledWith(
      'r-1',
      'safety:safety-commitment',
    )
    expect(mocks.message.success).toHaveBeenCalled()
  })

  it('无操作权限时隐藏编辑与发布按钮', async () => {
    mocks.canOperate = false
    await renderPanel()
    expect(buttons('编辑')).toHaveLength(0)
    expect(buttons('发布承诺公告')).toHaveLength(0)
    mocks.canOperate = true
  })

  it('初始错误时展示错误提示并保留重试', async () => {
    await renderPanel({ initialError: '数据库不可用' })
    const text = document.body.textContent ?? ''
    expect(text).toContain('安全承诺加载失败')
    // PlatformNotice 的详细描述在「了解访问规则」弹窗内，页面文本只含摘要
    expect(buttons('重试').length).toBeGreaterThan(0)
  })
})
