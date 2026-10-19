/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/auth'

const actions = vi.hoisted(() => ({
  getPressureRecords: vi.fn(),
  getAuditStats: vi.fn(),
  auditPressureRecord: vi.fn(),
  batchAuditPressureRecords: vi.fn(),
  createOcrTask: vi.fn(),
  submitOcrTaskResult: vi.fn(),
}))
vi.mock('@/actions/pressure', () => actions)

import AuditManagementPage from './audit/page'
import OcrInputPage from './ocr-input/page'

function setUser(sensitiveActions: string[], operate = true) {
  useAuthStore.getState().setUser({
    id: 'pressure-test', name: '压差权限测试', role: 'user',
    permissions: ['*'],
    page_permissions: [{
      page_key: 'production:pressure', module_code: 'production', source: 'user',
      permissions: operate ? ['access', 'query', 'operate'] : ['access', 'query'],
      sensitive_actions: sensitiveActions, data_scope: { scope_type: 'all' },
    }],
  })
}

describe('pressure page sensitive permissions', () => {
  let root: Root
  let container: HTMLElement

  beforeEach(() => {
    setUser([])
    actions.getPressureRecords.mockResolvedValue({
      code: 200, data: [{
        id: 'record-1', point_id: 'test-point', area: '其他', pressure_value: 1,
        standard_pressure: 0, record_time: '2026-10-16T08:00:00',
        input_type: 'manual', status: 'pending',
      }], meta: { total: 1 },
    })
    actions.getAuditStats.mockResolvedValue({
      code: 200, data: { pending_count: 1, today_approved_count: 0, rejected_count: 0 },
    })
    actions.auditPressureRecord.mockResolvedValue({ code: 200 })
    actions.createOcrTask.mockResolvedValue({
      code: 200, data: { id: 'ocr-task-1', result: { records: [{
        point_id: 'test-point', pressure_value: 1, time_slot: '上午',
        record_time: '2026-10-16T08:00:00', recorder: '测试',
      }] } },
    })
    actions.submitOcrTaskResult.mockResolvedValue({ code: 200, data: { success_count: 1 } })
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    useAuthStore.getState().clearUser()
    vi.clearAllMocks()
  })

  async function render(page: 'audit' | 'ocr') {
    await act(async () => {
      root.render(<App>{page === 'audit' ? <AuditManagementPage /> : <OcrInputPage />}</App>)
      await new Promise(r => setTimeout(r, 80))
    })
  }

  it.each([
    { grants: [], approve: false, reject: false },
    { grants: ['approve'], approve: true, reject: false },
    { grants: ['reject'], approve: false, reject: true },
  ])('separates audit buttons: $grants', async ({ grants, approve, reject }) => {
    setUser(grants)
    await render('audit')
    expect(Boolean(container.querySelector('[aria-label="通过记录"]'))).toBe(approve)
    expect(Boolean(container.querySelector('[aria-label="驳回记录"]'))).toBe(reject)
    expect(actions.auditPressureRecord).not.toHaveBeenCalled()
  })

  it('closes a pending rejection when its grant is revoked', async () => {
    setUser(['reject'])
    await render('audit')
    await act(async () => {
      container.querySelector<HTMLButtonElement>('[aria-label="驳回记录"]')!.click()
      await new Promise(r => setTimeout(r, 40))
    })
    expect(document.querySelector('.ant-modal textarea')).toBeTruthy()
    await act(async () => {
      setUser(['approve'])
      await new Promise(r => setTimeout(r, 400))
    })
    expect(container.querySelector('[aria-label="驳回记录"]')).toBeNull()
    const visibleRejectModal = [...document.querySelectorAll<HTMLElement>('.ant-modal-wrap')]
      .some(el => el.style.display !== 'none')
    expect(visibleRejectModal).toBe(false)
    expect(actions.auditPressureRecord).not.toHaveBeenCalled()
  })

  it.each([
    { grants: [], operate: true, enabled: false },
    { grants: ['bulk_import'], operate: false, enabled: false },
    { grants: ['bulk_import'], operate: true, enabled: true },
  ])('requires operate and bulk import for OCR: $grants/$operate', async ({ grants, operate, enabled }) => {
    setUser(grants, operate)
    await render('ocr')
    expect(container.querySelector<HTMLInputElement>('input[type="file"]')!.disabled).toBe(!enabled)
    expect(actions.createOcrTask).not.toHaveBeenCalled()
  })

  it('revokes OCR submission immediately and allows it again after reauthorization', async () => {
    setUser(['bulk_import'])
    await render('ocr')
    const input = container.querySelector<HTMLInputElement>('input[type="file"]')!
    Object.defineProperty(input, 'files', { value: [new File(['test'], 'test.png', { type: 'image/png' })] })
    await act(async () => {
      input.dispatchEvent(new Event('change', { bubbles: true }))
      await new Promise(r => setTimeout(r, 150))
    })
    expect(actions.createOcrTask).toHaveBeenCalledOnce()
    const submit = () => [...container.querySelectorAll('button')].find(b => b.textContent?.trim() === '提交')
    expect(submit()).toBeTruthy()
    await act(async () => { setUser([]) })
    expect(submit()).toBeUndefined()
    expect(actions.submitOcrTaskResult).not.toHaveBeenCalled()
    await act(async () => { setUser(['bulk_import']) })
    await act(async () => {
      submit()!.click()
      await new Promise(r => setTimeout(r, 50))
    })
    expect(actions.submitOcrTaskResult).toHaveBeenCalledWith('ocr-task-1', {
      records: [expect.objectContaining({ point_id: 'test-point', pressure_value: 1 })],
    })
    expect(container.textContent).toContain('提交成功')
  })
})
