import { beforeEach, describe, expect, it, vi } from 'vitest'

const pageApi = vi.hoisted(() => ({
  fetchPurchaseRequests: vi.fn(),
  getAuthHeaders: vi.fn(),
}))

vi.mock('next/navigation', () => ({
  notFound: vi.fn(() => {
    throw new Error('NOT_FOUND')
  }),
}))

vi.mock('@/lib/api/purchasing', () => ({
  fetchPurchaseRequests: pageApi.fetchPurchaseRequests,
}))

vi.mock('@/lib/auth', () => ({
  getAuthHeaders: pageApi.getAuthHeaders,
}))

vi.mock('@/components/purchasing', () => ({
  PurchaseApprovalClient: (props: Record<string, unknown>) => (
    <div data-page="approval">{String(props.category)}:{String(props.approvalRole)}:{String(props.initialTotal)}</div>
  ),
  PurchaseRequestFormClient: (props: Record<string, unknown>) => (
    <div data-page="urgent">{String(props.category)}:{String(props.categoryLabel)}:{String(props.initialTotal)}</div>
  ),
  approvalRoleToStep: {
    hardware_warehouse: 'hardware-warehouse',
    department_head: 'department-head',
    responsible_leader: 'responsible-leader',
    supervising_leader: 'supervising-leader',
    finance_director: 'finance-director',
    general_manager: 'general-manager',
  },
  approvalStepToRole: {
    'hardware-warehouse': 'hardware_warehouse',
    'department-head': 'department_head',
    'responsible-leader': 'responsible_leader',
    'supervising-leader': 'supervising_leader',
    'finance-director': 'finance_director',
    'general-manager': 'general_manager',
  },
  purchaseApprovalWorkflows: {
    hardware: ['hardware_warehouse', 'department_head'],
    urgent: [
      'hardware_warehouse',
      'department_head',
      'responsible_leader',
      'supervising_leader',
      'finance_director',
      'general_manager',
    ],
  },
  purchaseCategoryLabels: {
    hardware: '五金材料',
    urgent: '加急单',
  },
}))

import ApprovalPage, {
  generateStaticParams,
} from '@/app/(dashboard)/purchasing/approval/[category]/[step]/page'
import UrgentPurchaseRequestPage from '@/app/(dashboard)/purchasing/request/urgent/page'

const response = {
  code: 200,
  message: 'success',
  data: [],
  meta: { page: 1, page_size: 20, total: 0 },
}

describe('purchasing server pages', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    pageApi.getAuthHeaders.mockResolvedValue({})
    pageApi.fetchPurchaseRequests.mockResolvedValue(response)
  })

  it('generates only configured approval workflow paths', () => {
    expect(generateStaticParams()).toEqual([
      { category: 'hardware', step: 'hardware-warehouse' },
      { category: 'hardware', step: 'department-head' },
      { category: 'urgent', step: 'hardware-warehouse' },
      { category: 'urgent', step: 'department-head' },
      { category: 'urgent', step: 'responsible-leader' },
      { category: 'urgent', step: 'supervising-leader' },
      { category: 'urgent', step: 'finance-director' },
      { category: 'urgent', step: 'general-manager' },
    ])
  })

  it('loads a valid approval page and falls back when the API is unavailable', async () => {
    const result = await ApprovalPage({
      params: Promise.resolve({ category: 'urgent', step: 'department-head' }),
    })
    expect(result.props).toMatchObject({ category: 'urgent', approvalRole: 'department_head', initialTotal: 0 })
    expect(pageApi.fetchPurchaseRequests).toHaveBeenCalledWith(
      expect.objectContaining({ category: 'urgent', approval_role: 'department_head' }),
      {},
    )

    pageApi.fetchPurchaseRequests.mockRejectedValueOnce(new Error('network'))
    const fallback = await ApprovalPage({
      params: Promise.resolve({ category: 'urgent', step: 'department-head' }),
    })
    expect(fallback.props).toMatchObject({ category: 'urgent', approvalRole: 'department_head', initialTotal: 0 })
  })

  it('rejects an approval step outside the category workflow', async () => {
    await expect(ApprovalPage({
      params: Promise.resolve({ category: 'hardware', step: 'responsible-leader' }),
    })).rejects.toThrow('NOT_FOUND')
  })

  it('loads the urgent request page and handles the fallback response', async () => {
    const result = await UrgentPurchaseRequestPage()
    expect(result.props).toMatchObject({ category: 'urgent', categoryLabel: '加急单', initialTotal: 0 })
    expect(pageApi.fetchPurchaseRequests).toHaveBeenCalledWith(
      { category: 'urgent', page: 1, page_size: 20 },
      {},
    )

    pageApi.fetchPurchaseRequests.mockRejectedValueOnce(new Error('network'))
    const fallback = await UrgentPurchaseRequestPage()
    expect(fallback.props).toMatchObject({ category: 'urgent', categoryLabel: '加急单', initialTotal: 0, initialLoadFailed: true })
  })
})
