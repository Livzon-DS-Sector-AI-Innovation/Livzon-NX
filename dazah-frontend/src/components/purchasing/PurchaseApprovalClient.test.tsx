import { renderToStaticMarkup } from 'react-dom/server'
import { App } from 'antd'
import { describe, expect, it, vi } from 'vitest'
import {
  PurchaseApprovalClient,
  shouldDisableApprovalActions,
} from './PurchaseApprovalClient'

vi.mock('@/actions/purchasing', () => ({
  approvePurchaseRequest: vi.fn(),
  rejectPurchaseRequest: vi.fn(),
}))

vi.mock('@/lib/api/purchasing', () => ({
  fetchPurchaseRequests: vi.fn(),
}))

describe('PurchaseApprovalClient', () => {
  it('enables approval actions only after hydration', () => {
    expect(shouldDisableApprovalActions(false)).toBe(true)
    expect(shouldDisableApprovalActions(true)).toBe(false)
  })

  it('keeps approval actions disabled until client hydration completes', () => {
    const markup = renderToStaticMarkup(
      <App>
        <PurchaseApprovalClient
          category="hardware"
          categoryLabel="五金"
          approvalRole="department_head"
          initialRequests={[
            {
              id: '22222222-2222-2222-2222-222222222222',
              category: 'hardware',
              request_department: '工程设备部',
              request_date: '2026-07-29',
              attachment_note: '',
              total_amount: '1280.00',
              status: 'pending_department_head',
              items: [],
              approvals: [],
            },
          ]}
          initialTotal={1}
        />
      </App>
    )

    expect(markup).toMatch(
      /<button[^>]+disabled[^>]*>[\s\S]*?驳回[\s\S]*?<\/button>/
    )
  })
})
