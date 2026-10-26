/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App, ConfigProvider, theme } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { Bot } from '@/lib/api/energy-ledger'

vi.mock('@/actions/energy-ledger', () => ({

  saveLedgerBot: vi.fn(), retryLedgerNotification: vi.fn(),
}))
vi.mock('@/lib/api/energy-ledger', async original => ({
  ...await original<typeof import('@/lib/api/energy-ledger')>(), ledgerRequest: vi.fn(),
}))
vi.mock('./EnergyImportClient', () => ({ EnergyImportClient: () => <div>能源历史导入</div> }))
vi.mock('./EnergyReviewClient', () => ({ EnergyReviewClient: () => <div>待确认复核</div> }))
import * as actions from '@/actions/energy-ledger'
import { ledgerRequest } from '@/lib/api/energy-ledger'
import { EnergySettingsClient } from './EnergySettingsClient'

const bot: Bot = { version: 6, secret_configured: true, definition: { app_id: 'test-app', base_url: 'https://example.test', enabled: false } }
let root: Root | undefined
let client: QueryClient
const tick = () => new Promise(resolve => setTimeout(resolve, 30))
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(ledgerRequest).mockImplementation(async path => {
    const data: Record<string, unknown> = {
      '/input-fields': [], '/workbook-formulas': [], '/bot-config': bot,
      '/notification-runs': [{ id: 'notice-1', attempts: 2, status: 'failed', error: '发送超时' }],
    }
    return data[path]
  })
})
afterEach(async () => { await act(async () => root?.unmount()); client?.clear(); root = undefined; document.body.replaceChildren() })
async function render(manager = true, dark = false) {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const host = document.createElement('div'); document.body.append(host); root = createRoot(host)
  await act(async () => {
    root?.render(<QueryClientProvider client={client}><ConfigProvider locale={zhCN} theme={{ algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm, token: { motion: false } }}><App>
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
  await act(async () => { target!.click() })
  await act(async () => { await tick() })
}
it('blocks non-managers and does not fetch configuration', async () => {
  await render(false)
  expect(document.body.textContent).toContain('需要能源配置管理操作权限')
  expect(ledgerRequest).not.toHaveBeenCalled()
})
it.each([false, true])('keeps the retained tabs and avoids removed configuration requests (dark=%s)', async dark => {
  await render(true, dark)
  expect([...document.querySelectorAll('[role=tab]')].map(node => node.textContent)).toEqual(['飞书机器人', 'Excel 导入', '待确认复核'])
  expect(ledgerRequest).toHaveBeenCalledWith('/bot-config')
  expect(ledgerRequest).toHaveBeenCalledWith('/notification-runs')
  expect(ledgerRequest).not.toHaveBeenCalledWith('/input-fields')
  await tab('Excel 导入')
  expect(document.body.textContent).toContain('能源历史导入')
  expect(ledgerRequest).toHaveBeenCalledWith('/input-fields')
  expect(ledgerRequest).not.toHaveBeenCalledWith('/workbook-formulas')
  expect(ledgerRequest).not.toHaveBeenCalledWith('/entry-plans')
  expect(ledgerRequest).not.toHaveBeenCalledWith('/period-locks')
  for (const label of ['新增计量点', '新增计算指标', '新增填报分组', '试算该日', '重算该月', '封账该月', '应用人工调整']) expect(document.body.textContent).not.toContain(label)
  expect(document.querySelector('[role=dialog]')).toBeNull()
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
it('retains bot inputs after a failed save and permits a successful retry', async () => {
  vi.mocked(actions.saveLedgerBot).mockResolvedValueOnce({ ok: false, message: '机器人配置未保存' }).mockResolvedValueOnce({ ok: true, data: bot })
  await render()
  await click('保存机器人配置')
  expect(document.body.textContent).toContain('机器人配置未保存')
  expect(document.querySelector<HTMLInputElement>('input')?.value).toBe(bot.definition.app_id)
  await click('保存机器人配置')
  expect(actions.saveLedgerBot).toHaveBeenCalledTimes(2)
})
it.each([false, true])('keeps import configuration failures retryable without exposing removed pages (dark=%s)', async dark => {
  vi.mocked(ledgerRequest).mockImplementation(async path => {
    if (path === '/input-fields' || path === '/workbook-formulas') throw new Error('导入映射暂不可用')
    return path === '/bot-config' ? bot : []
  })
  await render(true, dark)
  await tab('Excel 导入')
  expect(document.body.textContent).toContain('导入映射暂不可用')
  expect(document.body.textContent).not.toContain('能源历史导入')
  vi.mocked(ledgerRequest).mockResolvedValue([])
  await click('重试')
  expect(document.body.textContent).toContain('能源历史导入')
  expect([...document.querySelectorAll('[role=tab]')].map(node => node.textContent)).toEqual(['飞书机器人', 'Excel 导入', '待确认复核'])
})
