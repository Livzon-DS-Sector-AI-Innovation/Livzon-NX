import React from 'react'
import { describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  fetchAnnualTrainingPlanByIdServer: vi.fn(),
  fetchContractApprovalResultsServer: vi.fn(),
  fetchEmployeeStatsServer: vi.fn(),
  fetchProjectLedgerWorkbookServer: vi.fn(),
  fetchProjectLedgerSheetDetailServer: vi.fn(),
  fetchAuthorizationLedgerServer: vi.fn(),
  fetchAuthorizationFdaServer: vi.fn(),
  fetchDeclarationProgressWorkbookServer: vi.fn(),
  fetchDeclarationProgressSheetDetailServer: vi.fn(),
  fetchDeviationServer: vi.fn(),
  updateDeviation: vi.fn(),
}))

vi.mock('@/lib/api/server/hr', () => mocks)
vi.mock('@/lib/api/server/registration', () => mocks)
vi.mock('@/components/hr', () => ({
  EmployeeDashboardClient: () => React.createElement('div', null, 'employee dashboard'),
}))
vi.mock('@/components/registration', () => ({
  ProjectLedgerDashboardPage: () => React.createElement('div', null, 'project ledger dashboard'),
  AuthorizationLetterClient: () => React.createElement('div', null, 'authorization letters'),
  DeclarationProgressDashboardPage: () => React.createElement('div', null, 'declaration progress'),
}))
vi.mock('@/components/hr/ContractApprovalResultsClient', () => ({
  default: () => React.createElement('div', null, 'approval results'),
}))
vi.mock('@/components/hr/AnnualPlanListClient', () => ({
  default: () => React.createElement('div', null, 'annual plan list'),
}))
vi.mock('@/components/hr/AnnualPlanDeptClient', () => ({
  default: () => React.createElement('div', null, 'annual plan department'),
}))
vi.mock('@/components/hr/AnnualPlanDetailClient', () => ({
  default: () => React.createElement('div', null, 'annual plan detail'),
}))
vi.mock('@/components/quality', () => ({
  DeviationDetail: () => React.createElement('div', null, 'deviation detail'),
  QualityQueryProvider: ({ children }: { children: React.ReactNode }) => React.createElement('div', null, children),
}))
vi.mock('@/actions/quality-deviation', () => ({
  updateDeviation: mocks.updateDeviation,
}))
vi.mock('next/navigation', () => ({
  redirect: vi.fn(),
}))

describe('migrated server page coverage', () => {
  it('keeps contract approval results available when the query fails', async () => {
    mocks.fetchContractApprovalResultsServer.mockRejectedValueOnce(new Error('offline'))
    const { default: ContractApprovalResultsPage } = await import(
      './app/(dashboard)/hr/contracts/approval-results/page'
    )

    expect(await ContractApprovalResultsPage()).toBeTruthy()
  })

  it('keeps employee management available when statistics fail', async () => {
    mocks.fetchEmployeeStatsServer.mockRejectedValueOnce(new Error('offline'))
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    const { default: EmployeeManagementPage } = await import(
      './app/(dashboard)/hr/employee-management/page'
    )

    expect(await EmployeeManagementPage()).toBeTruthy()
    expect(warn).toHaveBeenCalled()
    warn.mockRestore()
  })

  it('loads annual training metadata from the selected plan', async () => {
    mocks.fetchAnnualTrainingPlanByIdServer.mockResolvedValueOnce({
      data: { department: '质量部', year: 2026 },
    })
    const { generateMetadata } = await import(
      './app/(dashboard)/hr/training/annual-plan/page'
    )

    await expect(
      generateMetadata({ searchParams: Promise.resolve({ id: 'plan-1' }) }),
    ).resolves.toEqual({ title: '质量部2026年度培训计划' })
  })

  it('wraps OOS/OOT pages in the query provider', async () => {
    const { default: OosOotLayout } = await import(
      './app/(dashboard)/quality/oos-oot/layout'
    )

    expect(OosOotLayout({ children: React.createElement('span', null, 'content') })).toBeTruthy()
  })

  it('shows an error state when the project ledger workbook cannot load', async () => {
    mocks.fetchProjectLedgerWorkbookServer.mockRejectedValueOnce(new Error('offline'))
    const { default: ProjectLedgerPage } = await import(
      './app/(dashboard)/registration/project-ledger/page'
    )

    expect(await ProjectLedgerPage()).toBeTruthy()
  })

  it('covers authorization fallback and partial declaration progress', async () => {
    mocks.fetchAuthorizationLedgerServer.mockResolvedValueOnce({
      records: [],
      overview: {},
    })
    mocks.fetchAuthorizationFdaServer.mockRejectedValueOnce(new Error('offline'))
    const { default: AuthorizationLetterPage } = await import(
      './app/(dashboard)/registration/authorization-letter/page'
    )
    expect(await AuthorizationLetterPage()).toBeTruthy()

    mocks.fetchDeclarationProgressWorkbookServer.mockResolvedValueOnce({
      sheets: [{ sheet_key: 'ok' }, { sheet_key: 'slow' }],
    })
    mocks.fetchDeclarationProgressSheetDetailServer
      .mockResolvedValueOnce({ sheet_key: 'ok' })
      .mockRejectedValueOnce(new Error('timeout'))
    const { default: DeclarationProgressPage } = await import(
      './app/(dashboard)/registration/declaration-progress/page'
    )
    expect(await DeclarationProgressPage()).toBeTruthy()

    mocks.fetchDeclarationProgressWorkbookServer.mockRejectedValueOnce(new Error('offline'))
    expect(await DeclarationProgressPage()).toBeTruthy()
  })

  it('executes the deviation server action with normalized form values', async () => {
    mocks.fetchDeviationServer.mockResolvedValueOnce({ id: 'deviation-1' })
    const { default: DeviationDetailPage } = await import(
      './app/(dashboard)/quality/deviations/[id]/page'
    )
    const page = (await DeviationDetailPage({
      params: Promise.resolve({ id: 'deviation-1' }),
      searchParams: Promise.resolve({ edit: ['1'] }),
    })) as React.ReactElement<{
      children: React.ReactElement<{
        saveAction: (formData: FormData) => Promise<void>
      }>
    }>
    const formData = new FormData()
    formData.set('description', 'updated')
    formData.set('has_occurred_before', 'true')
    formData.set('level', 'major')
    await page.props.children.props.saveAction(formData)

    expect(mocks.updateDeviation).toHaveBeenCalledWith(
      'deviation-1',
      expect.objectContaining({ title: 'updated', has_occurred_before: true }),
    )
  })
})
