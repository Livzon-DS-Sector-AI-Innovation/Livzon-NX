import { describe, expect, it, vi } from 'vitest'

// SSR 页面兜底契约：后端不可用时各页面必须降级空数据正常渲染，
// 不允许抛错冒泡到整页错误边界（页面打不开 = 事故）。

vi.mock('@/actions/hr', () => ({
  fetchEmployees: vi.fn(async () => {
    throw new Error('offline')
  }),
  fetchJobPostingsServer: vi.fn(async () => {
    throw new Error('offline')
  }),
  fetchCandidateById: vi.fn(async () => {
    throw new Error('offline')
  }),
  fetchDepartureRecords: vi.fn(async () => {
    throw new Error('offline')
  }),
}))

vi.mock('@/lib/api/server/hr', () => ({
  fetchPositionTransfersServer: vi.fn(async () => {
    throw new Error('offline')
  }),
  fetchContractsServer: vi.fn(async () => {
    throw new Error('offline')
  }),
  fetchNewEmployeesServer: vi.fn(async () => {
    throw new Error('offline')
  }),
  fetchNewOnboardingRecordsServer: vi.fn(async () => {
    throw new Error('offline')
  }),
  fetchNewOffboardingRecordsServer: vi.fn(async () => {
    throw new Error('offline')
  }),
  fetchNewDepartureRecordsServer: vi.fn(async () => {
    throw new Error('offline')
  }),
  fetchNewDepartmentsServer: vi.fn(async () => {
    throw new Error('offline')
  }),
}))

describe('HR SSR pages degrade to empty data when backend fails', () => {
  it('roster page renders with empty data on fetch failure', async () => {
    const page = await import('./roster/page')
    await expect(page.default()).resolves.toBeDefined()
  })

  it('profile page renders with empty data on fetch failure', async () => {
    const page = await import('./profile/page')
    await expect(page.default()).resolves.toBeDefined()
  })

  it('recruitment page renders with empty data on fetch failure', async () => {
    const page = await import('./recruitment/page')
    await expect(page.default()).resolves.toBeDefined()
  })

  it('candidate detail page degrades to fallback view on fetch failure', async () => {
    const page = await import('./recruitment/[id]/page')
    const result = await page.default({ params: Promise.resolve({ id: 'missing' }) })
    expect(result).toBeDefined()
  })

  it('departure page renders with empty data on fetch failure', async () => {
    const page = await import('./departure/page')
    await expect(page.default()).resolves.toBeDefined()
  })

  it('position-transfer page renders with empty data on fetch failure', async () => {
    const page = await import('./position-transfer/page')
    await expect(page.default()).resolves.toBeDefined()
  })

  it('contracts page renders with empty data on fetch failure', async () => {
    const page = await import('./contracts/page')
    await expect(page.default()).resolves.toBeDefined()
  })

  it('new-factory pages render with empty data on fetch failure', async () => {
    for (const [name, module] of Object.entries({
      profile: await import('./new/profile/page'),
      onboarding: await import('./new/onboarding/page'),
      offboarding: await import('./new/offboarding/page'),
      departure: await import('./new/departure/page'),
      departments: await import('./new/departments/page'),
    })) {
      await expect(module.default(), name).resolves.toBeDefined()
    }
  })
})
