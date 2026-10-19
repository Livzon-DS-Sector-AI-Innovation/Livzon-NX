/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { App, ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { afterEach, describe, expect, it, vi } from 'vitest'

const state = vi.hoisted(() => ({ data: undefined as unknown, error: undefined as Error | undefined, params: 'task=t1', invalidate: vi.fn(), refetch: vi.fn() }))
vi.mock('next/navigation', () => ({ useRouter: () => ({ replace: vi.fn() }), useSearchParams: () => new URLSearchParams(state.params) }))
vi.mock('@tanstack/react-query', () => ({ useQueryClient: () => ({ invalidateQueries: state.invalidate }), useQuery: (options: { queryKey: string[] }) => options.queryKey[1] === 'task' ? { data: state.data, error: state.error, refetch: state.refetch } : { data: { items: [] }, refetch: state.refetch } }))
vi.mock('@/actions/energy-ledger', () => ({ generateLedgerTasks: vi.fn(), submitLedgerTask: vi.fn() }))
vi.mock('@/stores/auth', () => ({ useAuthStore: (selector: (state: { hasPagePermission: () => boolean }) => boolean) => selector({ hasPagePermission: () => true }) }))

import { EnergyEntryClient } from './EnergyEntryClient'
import { submitLedgerTask, generateLedgerTasks } from '@/actions/energy-ledger'
import type { Task } from '@/lib/api/energy-ledger'

afterEach(() => { state.data = undefined; state.error = undefined; state.params = 'task=t1'; document.body.innerHTML = ''; vi.clearAllMocks() })

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

const entryTask: Task = {
  id: 't1', name: '水表填报组', task_date: '2026-07-02', owner_ids: [], deadline_time: '10:00', total_count: 2, completed_count: 0,
  items: ['水表一', '水表二'].map((name, index) => ({ id: `r${index + 1}`, point_id: `p${index + 1}`, name,
    category: 'drinking_water', reading_date: '2026-07-02', unit: 'm3', precision: 3, reading_type: 'counter', frequency: 'daily',
    multiplier: '1', value: null, draft_value: null, previous_value: '0', previous_date: '2026-07-01', version: 2, submitted_at: null })),
}
async function entryRender() {
  const host = document.createElement('div'); document.body.append(host); const root = createRoot(host)
  await act(async () => root.render(<ConfigProvider locale={zhCN} theme={{ token: { motion: false } }}><App><EnergyEntryClient manager /></App></ConfigProvider>))
  return root
}
async function entryClick(label: string, scope: ParentNode = document) {
  const button = [...scope.querySelectorAll<HTMLButtonElement>('button')].find(node => node.textContent?.replace(/\s/g, '') === label)
  expect(button, label).toBeDefined()
  await act(async () => button!.click())
}
async function pasteColumn(text: string) {
  const event = new Event('paste', { bubbles: true, cancelable: true })
  Object.defineProperty(event, 'clipboardData', { value: { getData: () => text } })
  await act(async () => document.querySelector('input[aria-label="水表一本次填写"]')!.dispatchEvent(event))
}
it('saves pasted values as a draft, preserves them on failure and submits the same versioned data after confirmation', async () => {
  state.data = entryTask; state.params = 'task=t1&source=feishu'
  vi.mocked(submitLedgerTask).mockResolvedValueOnce({ ok: false, message: '月份已封账，输入已保留' })
    .mockResolvedValueOnce({ ok: true, data: entryTask }).mockResolvedValueOnce({ ok: true, data: entryTask })
  const root = await entryRender()
  await pasteColumn('10.5\n20')
  const unload = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(unload)
  expect(unload.defaultPrevented).toBe(true)
  await entryClick('保存草稿')
  expect(submitLedgerTask).toHaveBeenLastCalledWith('t1', { values: [
    { reading_id: 'r1', version: 2, value: '10.5', exception: undefined },
    { reading_id: 'r2', version: 2, value: '20', exception: undefined },
  ], draft: true, reason: '', source: 'feishu' })
  expect(document.body.textContent).toContain('月份已封账，输入已保留')
  expect(document.querySelector<HTMLInputElement>('input[aria-label="水表一本次填写"]')?.value).toMatch(/^10\.50*$/)
  expect(state.invalidate).not.toHaveBeenCalled()
  await entryClick('保存草稿'); expect(state.invalidate).toHaveBeenCalledWith({ queryKey: ['energy-ledger'] })
  await pasteColumn('11\n21'); await entryClick('提交生效')
  expect(submitLedgerTask).toHaveBeenCalledTimes(2)
  await entryClick('确定', document.querySelector('[role=dialog]')!)
  expect(submitLedgerTask).toHaveBeenLastCalledWith('t1', expect.objectContaining({ draft: false, source: 'feishu', values: [
    { reading_id: 'r1', version: 2, value: '11', exception: undefined }, { reading_id: 'r2', version: 2, value: '21', exception: undefined },
  ] }))
  await act(async () => root.unmount())
})
it('rejects an empty draft and invalid pasted values before calling the server', async () => {
  state.data = entryTask; const root = await entryRender()
  await entryClick('保存草稿'); expect(document.body.textContent).toContain('请填写至少一个计量点')
  await pasteColumn('1\n-2'); expect(document.body.textContent).toContain('粘贴内容须为一列非负数值')
  expect(submitLedgerTask).not.toHaveBeenCalled()
  await act(async () => root.unmount())
})
it('refreshes generated task lists on success and exposes a generation error for retry', async () => {
  vi.mocked(generateLedgerTasks).mockResolvedValueOnce({ ok: true, data: { items: [], total: 0 } })
    .mockResolvedValueOnce({ ok: false, message: '责任分组尚未启用' })
  const root = await entryRender()
  await entryClick('生成该日清单'); expect(state.refetch).toHaveBeenCalled()
  await entryClick('生成该日清单'); expect(document.body.textContent).toContain('责任分组尚未启用')
  await entryClick('重试'); expect(state.refetch).toHaveBeenCalledTimes(3)
  await act(async () => root.unmount())
})
