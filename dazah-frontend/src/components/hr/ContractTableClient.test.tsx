/* @vitest-environment happy-dom */

import { renderToStaticMarkup } from 'react-dom/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ContractTableClient from './ContractTableClient'
import type { ContractVM } from '@/lib/api/client/hr'

const flags = vi.hoisted(() => ({ canOperate: true, canDelete: false, canSync: false }))
vi.mock('@/hooks/usePagePermissions', () => ({ usePagePermissions: () => flags }))
vi.mock('@/actions/hr', () => ({
  deleteContractAction: vi.fn(), updateContractAction: vi.fn(), renewContractAction: vi.fn(),
  syncContractsFromFeishu: vi.fn(), updateContractSignStatusAction: vi.fn(),
}))

const contract: ContractVM = {
  id: 'acceptance-contract', employee_number: 'ACCEPTANCE', name: '验收员工',
  gender: null, dept_level1: null, dept_level2: null, position: null, job_level: null,
  domain_account: null, id_card: null, id_card_expiry: null, archive_number: null,
  contract_sequence: null, contract_start_1: null, contract_end_1: null,
  contract_start_2: null, contract_end_2: null, contract_start_3: null, contract_end_3: null,
  contract_start_4: null, contract_end_4: null, contract_start_5: null, contract_end_5: null,
  contract_start_6: null, contract_end_6: null, dept_leader_name: null, contract_opinion: null,
  approval_status: null, supervisor_name: null, supervisor_open_id: null, dept_approved_at: null,
  supervisor_approved_at: null, signed_status: null, signed_at: null, sign_reminded_at: null,
  created_at: '2026-09-15', updated_at: '2026-09-15',
}

function buttons() {
  const container = document.createElement('div')
  container.innerHTML = renderToStaticMarkup(<ContractTableClient initialData={[contract]} initialTotal={1} />)
  return (text: string) => Array.from(container.querySelectorAll('button'))
    .find(button => button.textContent?.replace(/\s/g, '') === text)
}

describe('contract page action permissions', () => {
  beforeEach(() => Object.assign(flags, { canOperate: true, canDelete: false, canSync: false }))

  it('keeps editing available without granting deletion or synchronization', () => {
    const button = buttons()
    expect(button('编辑')?.disabled).toBe(false)
    expect(button('删除')?.disabled).toBe(true)
    expect(button('同步飞书')?.disabled).toBe(true)
  })

  it('enables separately granted sensitive actions', () => {
    Object.assign(flags, { canDelete: true, canSync: true })
    const button = buttons()
    expect(button('删除')?.disabled).toBe(false)
    expect(button('同步飞书')?.disabled).toBe(false)
  })

  it('renders a read-only user without editing controls', () => {
    flags.canOperate = false
    const button = buttons()
    expect(button('编辑')).toBeUndefined()
    expect(button('详情')?.disabled).toBe(false)
    expect(button('同步飞书')?.disabled).toBe(true)
  })
})
