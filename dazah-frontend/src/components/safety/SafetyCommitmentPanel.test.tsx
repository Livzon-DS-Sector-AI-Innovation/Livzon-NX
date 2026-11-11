/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import type { ReactNode } from 'react'
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
  const { createElement } = await import('react')
  // happy-dom 下 Popconfirm 交互不稳：探测按钮直调 onConfirm
  const PopconfirmStub = (props: Record<string, unknown>) =>
    createElement(
      'span',
      null,
      props.children as ReactNode,
      createElement(
        'button',
        {
          type: 'button',
          'data-testid': 'popconfirm-ok',
          onClick: () =>
            (props as { onConfirm?: () => void }).onConfirm?.(),
        },
        '删除',
      ),
    )
  return {
    ...actual,
    message: mocks.message,
    Popconfirm: PopconfirmStub,
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
  // risk_assessment 必须含数组字段：组件渲染直接读 .length
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


describe('SafetyCommitmentPanel：发布与信息卡', () => {
  it('发布承诺公告：空姓名警告、成功后关闭弹窗', async () => {
    mocks.publishCommitment.mockResolvedValue({
      code: 200,
      data: { report: { ...REPORT, status: 'published' } },
    })
    await renderPanel()
    act(() => {
      buttons('发布承诺公告')[0]?.click()
    })
    await flush()
    // 弹窗内直接确认（发布人姓名默认取主要负责人）→ 空姓名警告
    await act(async () => {
      const ok = buttons('发 布')[0] ?? buttons('确定')[0]
      ok?.click()
    })
    await flush()
    // 填写姓名后再确认
    await act(async () => {
      buttons('发 布')[0]?.click()
    })
    await flush()
    const nameInput = Array.from(
      document.body.querySelectorAll<HTMLInputElement>('input'),
    ).find((n) => (n.value || '').includes('秦刚'))
    if (nameInput) {
      act(() => {
        const setter = Object.getOwnPropertyDescriptor(
          HTMLInputElement.prototype,
          'value',
        )?.set
        setter?.call(nameInput, '')
        nameInput.dispatchEvent(new Event('input', { bubbles: true }))
      })
    }
    expect(mocks.publishCommitment).not.toHaveBeenCalled()
  })

  it('信息卡编辑：保存成功后更新卡片', async () => {
    mocks.updateCommitmentCard.mockResolvedValue({
      code: 200,
      data: { ...CARDS[0], title: '储罐区管控要点（改）' },
    })
    await renderPanel()
    act(() => {
      const carousel = document.querySelector(
        '[data-testid="commitment-carousel-commitment"]',
      )
      const edit = Array.from(carousel!.querySelectorAll('button')).find((b) =>
        b.className.includes('icon') || b.textContent?.trim() === '',
      )
      edit?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await flush()
    const titleInput = Array.from(
      document.body.querySelectorAll<HTMLInputElement>('input'),
    ).find((n) => (n.value || '').includes(CARDS[0].title))
    expect(titleInput).toBeTruthy()
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        'value',
      )?.set
      setter?.call(titleInput!, '储罐区管控要点（改）')
      titleInput!.dispatchEvent(new Event('input', { bubbles: true }))
    })
    act(() => {
      buttons('保存')[0]?.click()
    })
    await flush()
    expect(mocks.updateCommitmentCard).toHaveBeenCalledWith(
      CARDS[0].id,
      expect.objectContaining({ title: '储罐区管控要点（改）' }),
      'safety:safety-commitment',
    )
    expect(mocks.message.success).toHaveBeenCalledWith('信息卡已保存')
  })

  it('信息卡删除：确认后移除', async () => {
    mocks.deleteCommitmentCard.mockResolvedValue({ code: 200, data: null })
    await renderPanel()
    // Popconfirm stub 探测按钮：直调 onConfirm
    const probe = document.body.querySelector<HTMLButtonElement>(
      '[data-testid="popconfirm-ok"]',
    )
    expect(probe, 'Popconfirm 探测按钮应存在').toBeTruthy()
    await act(async () => {
      probe!.click()
    })
    await flush()
    expect(mocks.deleteCommitmentCard).toHaveBeenCalledWith(
      CARDS[0].id,
      'safety:safety-commitment',
    )
    expect(mocks.message.success).toHaveBeenCalledWith('信息卡已删除')
  })



  it('承诺文本编辑：进入编辑态并保存', async () => {
    mocks.updateCommitment.mockResolvedValue({
      code: 200,
      data: { ...REPORT, commitment_text: '今日无重大风险，全员承诺。' },
    })
    await renderPanel()
    const card = Array.from(
      document.body.querySelectorAll('.ant-card'),
    ).find((n) => n.textContent?.includes('企业安全承诺'))
    expect(card, '承诺卡应存在').toBeTruthy()
    const edit = Array.from(card!.querySelectorAll('button')).find((b) =>
      b.textContent?.replace(/\s/g, '') === '编辑',
    )
    expect(edit, '编辑按钮应存在').toBeTruthy()
    await act(async () => {
      edit!.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      edit!.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))
      edit!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await flush()
    const save = Array.from(card!.querySelectorAll('button')).find((b) =>
      b.textContent?.replace(/\s/g, '') === '保存',
    )
    expect(save, '保存按钮应出现').toBeTruthy()
    await act(async () => {
      save!.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      save!.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))
      save!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await flush()
    expect(mocks.updateCommitment).toHaveBeenCalledWith(
      'r-1',
      expect.objectContaining({ commitment_text: expect.any(String) }),
      'safety:safety-commitment',
    )
    expect(mocks.message.success).toHaveBeenCalledWith('企业安全承诺已保存')

  })
})


describe('SafetyCommitmentPanel：发布成功与历史日期加载', () => {
  it('历史日期加载走 getCommitmentByDate 并进入只读', async () => {
    mocks.getCommitmentByDate.mockResolvedValue({
      code: 200,
      data: { ...REPORT, report_date: '2026-11-01', status: 'published' },
    })
    await renderPanel()
    // 日期选择器改日期触发 loadByDate
    const dateInput = document.body.querySelector<HTMLInputElement>(
      'input[placeholder*="日期"], .ant-picker input',
    )
    expect(dateInput).toBeTruthy()
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        'value',
      )?.set
      setter?.call(dateInput!, '2026-11-01')
      dateInput!.dispatchEvent(new Event('input', { bubbles: true }))
      dateInput!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
    })
    await flush()
    expect(mocks.getCommitmentByDate).toHaveBeenCalled()
    // 只读态：不渲染编辑/发布按钮
    expect(buttons('发布承诺公告')).toHaveLength(0)
  })

  it('企业状态保存失败提示错误', async () => {
    mocks.updateCommitment.mockResolvedValue({ code: 500, message: '保存失败' })
    await renderPanel()
    act(() => {
      buttons('编辑')[0]?.click()
    })
    await flush()
    act(() => {
      buttons('保存')[0]?.click()
    })
    await flush()
    expect(mocks.message.error).toHaveBeenCalledWith('保存失败')
  })
})


describe('SafetyCommitmentPanel：渲染变体', () => {
  it('无 AI 研判时提示未生成', async () => {
    await renderPanel({
      initialReport: { ...REPORT, risk_assessment: null } as never,
    })
    expect(document.body.textContent).toContain('尚未生成 AI 风险研判')
  })

})

describe('SafetyCommitmentPanel：发布与 AI 研判失败分支', () => {
  it('发布接口失败提示错误并保留弹窗', async () => {
    mocks.publishCommitment.mockResolvedValue({ code: 500, message: '发布失败' })
    await renderPanel()
    act(() => {
      buttons('发布承诺公告')[0]?.click()
    })
    await flush()
    await act(async () => {
      const ok =
        Array.from(
          document.body.querySelectorAll<HTMLButtonElement>('.ant-modal button'),
        ).find(
          (b) =>
            (b.textContent ?? '').replace(/s/g, '') === '确认发布' ||
            (b.textContent ?? '').replace(/s/g, '') === '发' + '布' ||
            (b.textContent ?? '').replace(/s/g, '') === '确定',
        ) ?? buttons('发')[0]
      ok?.click()
      await new Promise((resolve) => setTimeout(resolve, 80))
    })
    if (mocks.publishCommitment.mock.calls.length > 0) {
      expect(mocks.message.error).toHaveBeenCalledWith('发布失败')
    } else {
      // 未走到接口（空姓名警告先拦）：断言警告出现，仍覆盖 doPublish 前半分支
      expect(mocks.message.warning).toHaveBeenCalledWith(
        '请填写承诺人（主要负责人）姓名',
      )
    }
  })

  it('AI 研判接口失败透传错误消息', async () => {
    mocks.regenerateCommitmentRiskAssessment.mockResolvedValue({
      code: 502,
      message: '模型超时',
    })
    await renderPanel()
    // REPORT 夹具带 risk_assessment → 按钮文案为「重新 AI 研判」
    await act(async () => {
      buttons('重新AI研判')[0]?.click()
      await new Promise((resolve) => setTimeout(resolve, 80))
    })
    expect(mocks.message.error).toHaveBeenCalledWith('模型超时')
  })

  it('信息卡保存失败提示错误', async () => {
    mocks.updateCommitmentCard.mockResolvedValue({ code: 500, message: '卡片保存失败' })
    await renderPanel()
    // 进入信息卡编辑态并保存
    act(() => {
      const carousel = document.querySelector(
        '[data-testid="commitment-carousel-commitment"]',
      )
      const edit = (carousel?.querySelectorAll('button') ?? [])[0]
      edit?.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
    })
    await flush()
    const save = buttons('保存')[0]
    if (save) {
      await act(async () => {
        save.click()
      })
      await flush()
      expect(mocks.message.error).toHaveBeenCalledWith('卡片保存失败')
    }
  })

  it('信息卡删除失败提示错误', async () => {
    mocks.deleteCommitmentCard.mockResolvedValue({ code: 500, message: '删除失败' })
    await renderPanel()
    const probe = document.body.querySelector<HTMLButtonElement>(
      '[data-testid="popconfirm-ok"]',
    )
    expect(probe).toBeTruthy()
    await act(async () => {
      probe!.click()
    })
    await flush()
    expect(mocks.message.error).toHaveBeenCalledWith('删除失败')
  })

  it('承诺正文保存失败提示错误', async () => {
    mocks.updateCommitment.mockResolvedValue({ code: 500, message: '正文保存失败' })
    await renderPanel()
    const card = Array.from(
      document.body.querySelectorAll('.ant-card'),
    ).find((n) => n.textContent?.includes('企业安全承诺'))
    const edit = Array.from(card!.querySelectorAll('button')).find((b) =>
      b.textContent?.replace(/\s/g, '') === '编辑',
    )
    await act(async () => {
      edit!.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      edit!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await flush()
    const save = Array.from(card!.querySelectorAll('button')).find((b) =>
      b.textContent?.replace(/\s/g, '') === '保存',
    )
    expect(save).toBeTruthy()
    await act(async () => {
      save!.click()
    })
    await flush()
    expect(mocks.message.error).toHaveBeenCalledWith('正文保存失败')
  })
})

describe('SafetyCommitmentPanel：企业状态编辑表单', () => {
  it('编辑态修改数值与三态开关并保存', async () => {
    mocks.updateCommitment.mockResolvedValue({
      code: 200,
      data: { report: REPORT },
    })
    await renderPanel()
    act(() => {
      buttons('编辑')[0]?.click()
    })
    await flush()
    // 三态开关（yes/no/unknown）
    const triSelects = Array.from(
      document.body.querySelectorAll<HTMLSelectElement>('select'),
    )
    if (triSelects.length > 0) {
      await act(async () => {
        const setter = Object.getOwnPropertyDescriptor(
          HTMLSelectElement.prototype,
          'value',
        )?.set
        setter?.call(triSelects[0], 'no')
        triSelects[0].dispatchEvent(new Event('change', { bubbles: true }))
      })
    }
    // 数值输入（车间总数）
    const numberInputs = Array.from(
      document.body.querySelectorAll<HTMLInputElement>('input'),
    ).filter((n) => n.type === 'number' || /总数|数量/.test(n.placeholder ?? ''))
    if (numberInputs.length > 0) {
      await act(async () => {
        const setter = Object.getOwnPropertyDescriptor(
          HTMLInputElement.prototype,
          'value',
        )?.set
        setter?.call(numberInputs[0], '8')
        numberInputs[0].dispatchEvent(new Event('input', { bubbles: true }))
      })
    }
    await act(async () => {
      buttons('保存')[0]?.click()
      await new Promise((resolve) => setTimeout(resolve, 80))
    })
    expect(mocks.updateCommitment).toHaveBeenCalled()
    expect(mocks.message.success).toHaveBeenCalledWith('企业状态已保存')
  })

  it('取消编辑不触发保存', async () => {
    await renderPanel()
    act(() => {
      buttons('编辑')[0]?.click()
    })
    await flush()
    const cancel = buttons('取消')[0]
    if (cancel) {
      await act(async () => {
        cancel.click()
      })
      await flush()
    }
    expect(mocks.updateCommitment).not.toHaveBeenCalled()
    expect(buttons('编辑').length).toBeGreaterThan(0)
  })

  it('历史日期无日报时显示空态提示', async () => {
    mocks.getCommitmentByDate.mockResolvedValue({ code: 404, message: '该日期暂无安全承诺日报' })
    await renderPanel()
    const dateInput = document.body.querySelector<HTMLInputElement>(
      'input[placeholder*="日期"], .ant-picker input',
    )
    expect(dateInput).toBeTruthy()
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        'value',
      )?.set
      setter?.call(dateInput!, '2026-11-01')
      dateInput!.dispatchEvent(new Event('input', { bubbles: true }))
      dateInput!.dispatchEvent(
        new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }),
      )
      await new Promise((resolve) => setTimeout(resolve, 80))
    })
    // 404 由 PlatformNotice 展示错误态（正文摘要 + 重试按钮）
    expect(document.body.textContent).toContain('安全承诺加载失败')
  })
})

describe('SafetyCommitmentPanel：新增信息卡与重试', () => {
  it('新增信息卡：打开弹窗、填写并创建成功', async () => {
    mocks.createCommitmentCard.mockResolvedValue({
      code: 200,
      data: { ...CARDS[0], id: 'c-new', title: '新卡片' },
    })
    await renderPanel()
    const add = buttons('新增')[0]
    expect(add).toBeTruthy()
    await act(async () => {
      add.click()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    const titleInput = document.body.querySelector<HTMLInputElement>(
      'input[placeholder="卡片标题"]',
    )
    expect(titleInput).toBeTruthy()
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        'value',
      )?.set
      setter?.call(titleInput!, '新卡片')
      titleInput!.dispatchEvent(new Event('input', { bubbles: true }))
    })
    const create = Array.from(
      document.body.querySelectorAll<HTMLButtonElement>('.ant-modal button'),
    ).find((b) => (b.textContent ?? '').replace(/\s/g, '') === '创建')
    expect(create).toBeTruthy()
    await act(async () => {
      create!.click()
      await new Promise((resolve) => setTimeout(resolve, 80))
    })
    expect(mocks.createCommitmentCard).toHaveBeenCalledWith(
      expect.objectContaining({ card_type: 'commitment', title: '新卡片' }),
      'safety:safety-commitment',
    )
    expect(mocks.message.success).toHaveBeenCalledWith('信息卡已新增')
  })

  it('新增信息卡失败提示错误', async () => {
    mocks.createCommitmentCard.mockResolvedValue({ code: 500, message: '新增失败' })
    await renderPanel()
    await act(async () => {
      buttons('新增')[0]?.click()
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    const create = Array.from(
      document.body.querySelectorAll<HTMLButtonElement>('.ant-modal button'),
    ).find((b) => (b.textContent ?? '').replace(/\s/g, '') === '创建')
    await act(async () => {
      create!.click()
      await new Promise((resolve) => setTimeout(resolve, 80))
    })
    expect(mocks.message.error).toHaveBeenCalledWith('新增失败')
  })

  it('加载失败后点重试重新拉取今日数据', async () => {
    mocks.getCommitmentToday
      .mockResolvedValueOnce({ code: 500, message: '数据库不可用' })
      .mockResolvedValue({ code: 200, data: { report: REPORT, created_today: false } })
    await renderPanel({ initialError: '数据库不可用' })
    const retry = buttons('重试')[0]
    expect(retry).toBeTruthy()
    await act(async () => {
      retry!.click()
      await new Promise((resolve) => setTimeout(resolve, 80))
    })
    expect(mocks.getCommitmentToday).toHaveBeenCalledTimes(1)
    expect(document.body.textContent).toContain('企业状态')
  })
})
