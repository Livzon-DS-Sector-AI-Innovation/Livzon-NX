import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  fetchMaterialSourceConfig: vi.fn(),
  getAuthHeaders: vi.fn().mockResolvedValue({ Authorization: 'Bearer test' }),
  getCurrentUser: vi.fn(),
}))

vi.mock('next/navigation', () => ({
  notFound: vi.fn(() => {
    throw new Error('NOT_FOUND')
  }),
  redirect: vi.fn(() => {
    throw new Error('REDIRECT')
  }),
}))
vi.mock('@/actions/auth', () => ({ getCurrentUser: mocks.getCurrentUser }))
vi.mock('@/lib/auth', () => ({ getAuthHeaders: mocks.getAuthHeaders }))
vi.mock('@/lib/api/purchasing', () => ({
  fetchMaterialSourceConfig: mocks.fetchMaterialSourceConfig,
}))
vi.mock('@/components/purchasing', () => ({
  ProcurementMaterialSourceSettingsClient: (props: Record<string, unknown>) => (
    <div data-failed={String(props.initialLoadFailed)}>
      {props.initialConfig ? 'configured' : 'not-configured'}
    </div>
  ),
}))

import ProcurementSettingsPage from '@/app/(dashboard)/purchasing/settings/page'

describe('procurement settings page permissions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('redirects anonymous users and hides the page from non-admin users', async () => {
    mocks.getCurrentUser.mockResolvedValueOnce(null)
    await expect(ProcurementSettingsPage()).rejects.toThrow('REDIRECT')

    mocks.getCurrentUser.mockResolvedValueOnce({ role: 'user' })
    await expect(ProcurementSettingsPage()).rejects.toThrow('NOT_FOUND')
  })

  it('loads the saved source for an administrator', async () => {
    mocks.getCurrentUser.mockResolvedValue({ role: 'admin' })
    mocks.fetchMaterialSourceConfig.mockResolvedValue({ data: { id: 'config-1' } })

    const result = await ProcurementSettingsPage()

    expect(result.props).toMatchObject({
      initialConfig: { id: 'config-1' },
      initialLoadFailed: false,
    })
    expect(mocks.fetchMaterialSourceConfig).toHaveBeenCalledWith({
      Authorization: 'Bearer test',
    })
  })

  it('preserves the page with a visible load failure state', async () => {
    mocks.getCurrentUser.mockResolvedValue({ role: 'admin' })
    mocks.fetchMaterialSourceConfig.mockRejectedValue(new Error('network'))

    const result = await ProcurementSettingsPage()

    expect(result.props).toMatchObject({ initialConfig: null, initialLoadFailed: true })
  })
})
