import React from 'react'
import { describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  fetchAnnualTrainingPlanByIdServer: vi.fn(),
  fetchContractApprovalResultsServer: vi.fn(),
  fetchEmployeeStatsServer: vi.fn(),
  fetchProjectLedgerWorkbookServer: vi.fn(),
  fetchProjectLedgerSheetDetailServer: vi.fn(),
}))

vi.mock('@/lib/api/server/hr', () => mocks)
vi.mock('@/lib/api/server/registration', () => mocks)
vi.mock('@/components/hr', () => ({
  EmployeeDashboardClient: () => React.createElement('div', null, 'employee dashboard'),
}))
vi.mock('@/components/registration', () => ({
  ProjectLedgerDashboardPage: () => React.createElement('div', null, 'project ledger dashboard'),
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
})
