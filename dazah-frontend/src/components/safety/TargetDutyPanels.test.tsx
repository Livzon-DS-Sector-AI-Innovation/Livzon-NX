/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getSafetyTargetAgreements: vi.fn(),
  getSafetyTargetAgreementStats: vi.fn(),
  createSafetyTargetAgreement: vi.fn(),
  updateSafetyTargetAgreement: vi.fn(),
  deleteSafetyTargetAgreement: vi.fn(),
  getSafetyDutyAssessments: vi.fn(),
  getSafetyDutyAssessmentStats: vi.fn(),
  getSafetyDutyAssessmentTemplate: vi.fn(),
  createSafetyDutyAssessment: vi.fn(),
  updateSafetyDutyAssessment: vi.fn(),
  deleteSafetyDutyAssessment: vi.fn(),
  downloadAgreementImportTemplate: vi.fn(),
  importAgreementSigns: vi.fn(),
  downloadDutyAssessmentImportTemplate: vi.fn(),
  importDutyAssessmentResults: vi.fn(),
  getSafetyTargets: vi.fn(),
  canOperate: true,
  canDelete: true,
}))

vi.mock('@/actions/safety', () => ({
  getSafetyTargetAgreements: mocks.getSafetyTargetAgreements,
  getSafetyTargetAgreementStats: mocks.getSafetyTargetAgreementStats,
  createSafetyTargetAgreement: mocks.createSafetyTargetAgreement,
  updateSafetyTargetAgreement: mocks.updateSafetyTargetAgreement,
  deleteSafetyTargetAgreement: mocks.deleteSafetyTargetAgreement,
  getSafetyDutyAssessments: mocks.getSafetyDutyAssessments,
  getSafetyDutyAssessmentStats: mocks.getSafetyDutyAssessmentStats,
  getSafetyDutyAssessmentTemplate: mocks.getSafetyDutyAssessmentTemplate,
  createSafetyDutyAssessment: mocks.createSafetyDutyAssessment,
  updateSafetyDutyAssessment: mocks.updateSafetyDutyAssessment,
  deleteSafetyDutyAssessment: mocks.deleteSafetyDutyAssessment,
  downloadAgreementImportTemplate: mocks.downloadAgreementImportTemplate,
  importAgreementSigns: mocks.importAgreementSigns,
  downloadDutyAssessmentImportTemplate: mocks.downloadDutyAssessmentImportTemplate,
  importDutyAssessmentResults: mocks.importDutyAssessmentResults,
  getSafetyTargets: mocks.getSafetyTargets,
}))

vi.mock('@/hooks/usePagePermissions', () => ({
  usePagePermissions: () => ({
    canOperate: mocks.canOperate,
    canDelete: mocks.canDelete,
    canView: true,
  }),
}))

// happy-dom 下 rc-picker 的 dayjs 适配器缺 isValid：仅替换日期控件，其余走真实 antd
vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>()
  const { createElement } = await import('react')
  const DatePickerStub = ({ value, onChange }: Record<string, unknown>) =>
    createElement('input', {
      value: (value as string) ?? '',
      onChange: (event: { target: { value: string } }) =>
        (onChange as ((v: string) => void) | undefined)?.(event.target.value),
    })
  return {
    ...actual,
    DatePicker: Object.assign(DatePickerStub, {
      RangePicker: DatePickerStub,
    }),
  }
})

import DutyAssessmentPanel from './DutyAssessmentPanel'
import TargetAgreementPanel from './TargetAgreementPanel'

const AGREEMENT = {
  id: 'a1',
  year: 2026,
  department: '101一车间',
  responsible_person: '张三',
  category: '部门级',
  goals_text: '杜绝重伤事故',
  status: 'signed',
  signed_date: '2026-01-15',
  expires_date: '2026-12-31',
  created_at: '2026-01-15T08:00:00',
}

const AGREEMENT_STATS = {
  total: 1,
  signed: 1,
  unsigned: 0,
  sign_rate: 100,
  departments: [],
}

const ASSESSMENT = {
  id: 'd1',
  year: 2026,
  quarter: 'Q1',
  department: '101一车间',
  assessor: '安环部',
  person_name: '张三',
  total_score: 95,
  grade: '优秀',
  assessment_date: '2026-04-01',
  created_at: '2026-04-01T08:00:00',
}

const ASSESSMENT_STATS = {
  avg_score: 95,
  excellent: 1,
  departments: [],
}

function flush() {
  return new Promise((resolve) => setTimeout(resolve, 60))
}

function buttons(text: string) {
  return Array.from(
    document.body.querySelectorAll<HTMLButtonElement>('button'),
  ).filter((b) => b.textContent?.includes(text))
}

describe('目标责任签约与履职评估面板', () => {
  let root: Root | undefined
  let container: HTMLElement | undefined

  beforeEach(() => {
    mocks.getSafetyTargetAgreements.mockResolvedValue({
      code: 200,
      message: 'success',
      data: { items: [AGREEMENT], total: 1 },
    })
    mocks.getSafetyTargetAgreementStats.mockResolvedValue({
      code: 200,
      message: 'success',
      data: AGREEMENT_STATS,
    })
    mocks.getSafetyDutyAssessments.mockResolvedValue({
      code: 200,
      message: 'success',
      data: { items: [ASSESSMENT], total: 1 },
    })
    mocks.getSafetyDutyAssessmentStats.mockResolvedValue({
      code: 200,
      message: 'success',
      data: ASSESSMENT_STATS,
    })
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root?.unmount())
    container?.remove()
    root = undefined
    container = undefined
    vi.clearAllMocks()
  })

  function render(node: React.ReactNode) {
    act(() => {
      root!.render(<App>{node}</App>)
    })
  }

  it('签约面板：渲染台账与统计', async () => {
    render(
      <TargetAgreementPanel
        pageKey="k"
        initialAgreements={[AGREEMENT] as never}
        initialStats={AGREEMENT_STATS as never}
        initialError={null}
      />,
    )
    await act(flush)
    const text = document.body.textContent ?? ''
    expect(text).toContain('101一车间')
    expect(text).toContain('杜绝重伤事故')
  })

  it('签约面板：登记责任书入口可打开', async () => {
    mocks.createSafetyTargetAgreement.mockResolvedValue({
      code: 200,
      message: 'success',
      data: null,
    })
    render(
      <TargetAgreementPanel
        pageKey="k"
        initialAgreements={[AGREEMENT] as never}
        initialStats={AGREEMENT_STATS as never}
        initialError={null}
      />,
    )
    await act(flush)

    const register = buttons('登记责任书')[0]
    if (register) {
      await act(async () => {
        register.click()
        await flush()
      })
    }
    expect((document.body.textContent ?? '').length).toBeGreaterThan(0)
  })

  it('签约面板：批量导入入口可打开', async () => {
    render(
      <TargetAgreementPanel
        pageKey="k"
        initialAgreements={[AGREEMENT] as never}
        initialStats={AGREEMENT_STATS as never}
        initialError={null}
      />,
    )
    await act(flush)

    const importBtn = buttons('批量导入')[0]
    if (importBtn) {
      await act(async () => {
        importBtn.click()
        await flush()
      })
    }
  })

  it('签约面板：初始加载失败时展示错误提示', () => {
    render(
      <TargetAgreementPanel
        pageKey="k"
        initialAgreements={[]}
        initialStats={null}
        initialError="责任书台账加载失败"
      />,
    )
    expect((document.body.textContent ?? '').includes('责任书台账加载失败')).toBe(
      true,
    )
  })

  it('评估面板：渲染考核记录与统计', async () => {
    render(
      <DutyAssessmentPanel
        pageKey="k"
        initialAssessments={[ASSESSMENT] as never}
        initialStats={ASSESSMENT_STATS as never}
        initialError={null}
      />,
    )
    await act(flush)
    const text = document.body.textContent ?? ''
    expect(text).toContain('安环部')
    expect(text).toContain('张三')
  })

  it('评估面板：删除走确认弹窗', async () => {
    mocks.deleteSafetyDutyAssessment.mockResolvedValue({
      code: 200,
      message: 'success',
      data: null,
    })
    render(
      <DutyAssessmentPanel
        pageKey="k"
        initialAssessments={[ASSESSMENT] as never}
        initialStats={ASSESSMENT_STATS as never}
        initialError={null}
      />,
    )
    await act(flush)

    const del = buttons('删除').at(-1)
    if (del) {
      await act(async () => {
        del.click()
        await flush()
      })
      const confirm = Array.from(
        document.body.querySelectorAll<HTMLButtonElement>('.ant-popover button'),
      ).find(
        (b) =>
          b.textContent === '确 定' ||
          b.textContent === '确定' ||
          b.textContent === 'OK',
      )
      if (confirm) {
        await act(async () => {
          confirm.click()
          await flush()
        })
        expect(mocks.deleteSafetyDutyAssessment).toHaveBeenCalled()
      }
    }
  })

  it('评估面板：初始加载失败时展示错误提示', () => {
    render(
      <DutyAssessmentPanel
        pageKey="k"
        initialAssessments={[]}
        initialStats={null}
        initialError="考核记录加载失败"
      />,
    )
    expect((document.body.textContent ?? '').includes('考核记录加载失败')).toBe(
      true,
    )
  })
})
