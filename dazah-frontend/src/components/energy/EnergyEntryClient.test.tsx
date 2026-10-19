/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, describe, expect, it, vi } from 'vitest'

const state = vi.hoisted(() => ({ data: undefined as unknown, error: undefined as Error | undefined }))
vi.mock('next/navigation', () => ({ useRouter: () => ({ replace: vi.fn() }), useSearchParams: () => new URLSearchParams('task=t1') }))
vi.mock('@tanstack/react-query', () => ({ useQueryClient: () => ({ invalidateQueries: vi.fn() }), useQuery: (options: { queryKey: string[] }) => options.queryKey[1] === 'task' ? { data: state.data, error: state.error, refetch: vi.fn() } : { data: { items: [] }, refetch: vi.fn() } }))
vi.mock('@/actions/energy-ledger', () => ({ generateLedgerTasks: vi.fn(), submitLedgerTask: vi.fn() }))
vi.mock('@/stores/auth', () => ({ useAuthStore: (selector: (state: { hasPagePermission: () => boolean }) => boolean) => selector({ hasPagePermission: () => true }) }))

import { EnergyEntryClient } from './EnergyEntryClient'

afterEach(() => { state.data = undefined; state.error = undefined; document.body.innerHTML = '' })

describe('energy entry user-visible states', () => {
  it('includes a persisted zero draft in the submission confirmation', async () => {
    state.data = { id: 't1', name: '电表组', task_date: '2026-07-02', deadline_time: '10:00', total_count: 1, completed_count: 0, items: [{ id: 'r1', point_id: 'p1', name: '草稿电量', category: 'electricity', reading_date: '2026-07-01', unit: 'kWh', precision: 3, reading_type: 'direct', value: null, draft_value: '0', previous_value: null, previous_date: null, version: 2, submitted_at: null }] }
    const node = document.createElement('div'); document.body.append(node)
    const root = createRoot(node)
    await act(async () => root.render(<App><EnergyEntryClient manager={false} /></App>))
    const submit = Array.from(node.querySelectorAll('button')).find(button => button.textContent === '提交生效')
    await act(async () => submit?.click())
    const dialog = document.querySelector('[role="dialog"]')
    expect(dialog?.textContent).toContain('本次填写 1 项')
    expect(dialog?.textContent).toContain('草稿电量（2026-07-01）：— → 0 kWh')
    await act(async () => root.unmount())
  })
  it('shows a permission failure as a failure, not as empty tasks', async () => {
    state.error = new Error('当前任务未分配给您')
    const node = document.createElement('div'); document.body.append(node)
    const root = createRoot(node)
    await act(async () => root.render(<App><EnergyEntryClient manager={false} /></App>))
    expect(node.textContent).toContain('当前任务未分配给您')
    expect(node.textContent).toContain('提交即生效')
    await act(async () => root.unmount())
  })
  it('renders true zero readings without filling the next input automatically', async () => {
    state.data = { id: 't1', name: '水表组', task_date: '2026-07-02', deadline_time: '10:00', total_count: 1, completed_count: 1, items: [{ id: 'r1', point_id: 'p1', name: '101车间水表', category: 'drinking_water', reading_date: '2026-07-02', unit: 'm3', precision: 3, reading_type: 'counter', multiplier: '1', value: '0', draft_value: null, previous_value: '0', previous_date: '2026-07-01', version: 1, submitted_at: null }] }
    const node = document.createElement('div'); document.body.append(node)
    const root = createRoot(node)
    await act(async () => root.render(<App><EnergyEntryClient manager={false} /></App>))
    expect(node.textContent).toContain('已生效')
    expect(node.querySelector('input[aria-label="101车间水表本次填写"]')?.getAttribute('value')).not.toBe('0')
    expect(node.textContent).not.toContain('大罐数量')
    await act(async () => root.unmount())
  })
})
