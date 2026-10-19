/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App, ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import dayjs from 'dayjs'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { Meter, Rule, Plan, Bot } from '@/lib/api/energy-ledger'

vi.mock('@/actions/energy-ledger', () => ({
  saveLedgerMeter: vi.fn(), saveLedgerRule: vi.fn(), saveLedgerPlan: vi.fn(),
  saveLedgerBot: vi.fn(), saveLedgerLock: vi.fn(), retryLedgerNotification: vi.fn(),
  adjustLedgerUsage: vi.fn(), rebuildLedgerReports: vi.fn(), trialLedgerRules: vi.fn(),
}))
vi.mock('@/lib/api/energy-ledger', async original => ({
  ...await original<typeof import('@/lib/api/energy-ledger')>(), ledgerRequest: vi.fn(),
}))
vi.mock('./EnergyImportClient', () => ({ EnergyImportClient: () => <div>能源历史导入</div> }))
import * as actions from '@/actions/energy-ledger'
import { ledgerRequest } from '@/lib/api/energy-ledger'
import { EnergySettingsClient } from './EnergySettingsClient'

const meter: Meter = { id: 'meter-1', version: 3, definition: {
  code: 'water', name: '101水表', category: 'drinking_water', area: '101', department: '101车间', unit: 'm3',
  active_from: '2026-07-01', reading_type: 'counter', frequency: 'daily', multiplier: '1', precision: 3,
  report_scope: 'source', quantity_kind: 'volume', enabled: true, notes: '', source_sheet: '', temperature: '', workshop: '101',
} }
const rule: Rule = { id: 'rule-1', version: 4, definition: {
  code: 'total', name: '车间合计', category: 'drinking_water', unit: 'm3', department: '101车间',
  terms: [{ metric_key: 'point:water', coefficient: '1' }], active_from: '2026-07-01',
  operation: 'sum', frequency: 'daily', report_scope: 'detail', quantity_kind: 'volume', enabled: true, notes: '', source_sheet: '饮用水用量', source_column: 3, temperature: '', workshop: '101',
} }
const plan: Plan = { id: 'plan-1', version: 5, definition: {
  name: '101水表组', point_ids: ['meter-1'], owner_ids: ['owner-1'],
  publish_time: '08:00', deadline_time: '10:00', reminder_time: '10:30', enabled: true, group_chat_id: '',
} }
const bot: Bot = { version: 6, secret_configured: true, definition: { app_id: 'test-app', base_url: 'https://example.test', enabled: false } }
let root: Root | undefined
let client: QueryClient
const tick = () => new Promise(resolve => setTimeout(resolve, 30))
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(ledgerRequest).mockImplementation(async path => {
    const data: Record<string, unknown> = {
      '/meter-points': [meter], '/calculation-rules': [rule], '/entry-plans': [plan], '/bot-config': bot,
      '/period-locks': [{ month: dayjs().subtract(1, 'month').format('YYYY-MM'), version: 2, locked: false }],
      '/notification-runs': [{ id: 'notice-1', attempts: 2, status: 'failed', error: '发送超时' }],
    }
    return data[path]
  })
})
afterEach(async () => { await act(async () => root?.unmount()); client?.clear(); root = undefined; document.body.replaceChildren() })
async function render(manager = true) {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const host = document.createElement('div'); document.body.append(host); root = createRoot(host)
  await act(async () => {
    root?.render(<QueryClientProvider client={client}><ConfigProvider locale={zhCN} theme={{ token: { motion: false } }}><App>
      <EnergySettingsClient options={{ is_manager: manager, people: [{ id: 'owner-1', name: '填报员', department: '101车间' }] }} />
    </App></ConfigProvider></QueryClientProvider>)
    await tick()
  })
}
async function click(label: string, scope: ParentNode = document) {
  const button = [...scope.querySelectorAll<HTMLButtonElement>('button')].find(node => node.textContent?.replace(/\s/g, '') === label)
  expect(button, label).toBeDefined()
  await act(async () => { button!.click(); await tick() })
}
async function tab(label: string) {
  const target = [...document.querySelectorAll<HTMLElement>('[role=tab]')].find(node => node.textContent === label)
  expect(target).toBeDefined()
  await act(async () => { target!.click(); await tick() })
}
async function fill(label: string, value: string) {
  const fieldLabel = [...document.querySelectorAll('label')].find(node => node.textContent === label)
  const field = document.getElementById(fieldLabel?.htmlFor ?? '')
    ?? document.querySelector(`[aria-label="${label}"]`)
  if (!(field instanceof HTMLInputElement || field instanceof HTMLTextAreaElement)) throw new Error(`Missing field ${label}`)
  await act(async () => {
    const prototype = field instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype
    Object.getOwnPropertyDescriptor(prototype, 'value')?.set?.call(field, value)
    field.dispatchEvent(new Event('input', { bubbles: true })); field.dispatchEvent(new Event('change', { bubbles: true }))
    await tick()
  })
}
it('blocks non-managers and does not fetch configuration', async () => {
  await render(false)
  expect(document.body.textContent).toContain('需要能源配置管理操作权限')
  expect(ledgerRequest).not.toHaveBeenCalled()
})
it.each([
  { tabName: '计量点', action: actions.saveLedgerMeter, item: meter, reasonLabel: '配置变更原因', succeed: () => vi.mocked(actions.saveLedgerMeter).mockResolvedValueOnce({ ok: true, data: meter }) },
  { tabName: '计算关系', action: actions.saveLedgerRule, item: rule, reasonLabel: '配置变更原因', succeed: () => vi.mocked(actions.saveLedgerRule).mockResolvedValueOnce({ ok: true, data: rule }) },
  { tabName: '责任分组', action: actions.saveLedgerPlan, item: plan, reasonLabel: '变更原因', succeed: () => vi.mocked(actions.saveLedgerPlan).mockResolvedValueOnce({ ok: true, data: plan }) },
])('saves a versioned $tabName change and retains the form when the server refuses it', async ({ tabName, action, item, reasonLabel, succeed }) => {
  vi.mocked(action).mockResolvedValueOnce({ ok: false, message: '配置版本已变化，请核对' })
  await render(); await tab(tabName)
  await click('配置', document.querySelector('.ant-tabs-tabpane-active')!)
  await fill(reasonLabel, '计量口径复核')
  await click('保存配置')
  expect(action).toHaveBeenCalledWith(item.id, { definition: expect.objectContaining(item.definition), reason: '计量口径复核', version: item.version })
  expect(document.body.textContent).toContain('配置版本已变化，请核对')
  expect(document.querySelector('[role=dialog]')).not.toBeNull()
  succeed()
  await click('保存配置')
  expect(action).toHaveBeenCalledTimes(2)
})
it.each(['新增计量点', '新增计算指标', '新增填报分组'])('opens %s with editable fields and cancels without saving', async label => {
  await render(); await tab(label === '新增计算指标' ? '计算关系' : label === '新增填报分组' ? '责任分组' : '计量点')
  await click(label)
  const dialog = document.querySelector('[role=dialog]')!
  expect(dialog.querySelector('input')).not.toBeNull()
  await click('取消', dialog)
  expect(actions.saveLedgerMeter).not.toHaveBeenCalled(); expect(actions.saveLedgerRule).not.toHaveBeenCalled(); expect(actions.saveLedgerPlan).not.toHaveBeenCalled()
})
it('trials a date without rebuilding until the explicit confirmation', async () => {
  vi.mocked(actions.trialLedgerRules).mockResolvedValue({ ok: true, data: { usage_date: '2026-07-02', values: [{ metric_key: 'rule:total', name: '车间合计', value: '12', status: 'complete' }] } })
  vi.mocked(actions.rebuildLedgerReports).mockResolvedValue({ ok: true, data: { rows: [], start_date: '2026-07-01', end_date: '2026-07-31', status: 'complete', totals: [], total_count: 0, entry_completed: 0, entry_total: 0 } })
  await render(); await tab('计算关系'); await fill('试算日期', '2026-07-02'); await click('试算该日')
  expect(actions.trialLedgerRules).toHaveBeenCalledWith('2026-07-02')
  expect(document.body.textContent).toContain('12')
  await click('重算该月'); expect(actions.rebuildLedgerReports).not.toHaveBeenCalled()
  await click('确定', document.querySelector('[role=dialog]')!)
  expect(actions.rebuildLedgerReports).toHaveBeenCalledWith('2026-07-01', '2026-07-31')
})
it('keeps configured bot secrets blank and retries only on explicit request', async () => {
  vi.mocked(actions.saveLedgerBot).mockResolvedValue({ ok: true, data: bot })
  vi.mocked(actions.retryLedgerNotification).mockResolvedValue({ ok: false, message: '通知仍不可达' })
  await render(); await tab('飞书机器人')
  expect(document.querySelector<HTMLInputElement>('input[type=password]')?.value).toBe('')
  await click('载入已保存配置'); await click('保存机器人配置')
  expect(actions.saveLedgerBot).toHaveBeenCalledWith({ definition: bot.definition, app_secret: undefined, version: 6 })
  await click('重试'); expect(actions.retryLedgerNotification).toHaveBeenCalledWith('notice-1')
  expect(document.body.textContent).toContain('通知仍不可达')
})
it('requires a reason and confirmation before locking the month', async () => {
  vi.mocked(actions.saveLedgerLock).mockResolvedValue({ ok: false, message: '存在未完成清单' })
  await render(); await tab('封账与调整')
  const lock = [...document.querySelectorAll<HTMLButtonElement>('button')].find(node => node.textContent === '封账该月')!
  expect(lock.disabled).toBe(true)
  await fill('封账或解锁原因', '月末核对'); await click('封账该月')
  expect(actions.saveLedgerLock).not.toHaveBeenCalled()
  await click('确定', document.querySelector('[role=dialog]')!)
  expect(actions.saveLedgerLock).toHaveBeenCalledWith(dayjs().subtract(1, 'month').format('YYYY-MM'), { locked: true, reason: '月末核对', version: 2 })
  expect(document.body.textContent).toContain('存在未完成清单')
})
it('preserves query errors and keeps historical sources accessible', async () => {
  vi.mocked(ledgerRequest).mockRejectedValue(new Error('能源配置暂不可用'))
  await render()
  expect(document.body.textContent).toContain('能源配置暂不可用')
  await tab('历史导入'); expect(document.body.textContent).toContain('能源历史导入')
  await tab('历史来源'); expect(document.querySelector('a[href="/energy/data"]')).not.toBeNull()
})
