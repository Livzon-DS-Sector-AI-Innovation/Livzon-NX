/* @vitest-environment happy-dom */
import { act, createElement } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AgentModuleCoverageClient from './AgentModuleCoverageClient'
import type { AgentModuleCoverageView } from '@/actions/settings'

const mocks = vi.hoisted(() => ({ load: vi.fn() }))
vi.mock('@/actions/settings', () => ({ getAgentModuleCoverage: mocks.load }))
const data: AgentModuleCoverageView = {
  generated_at: '2026-10-10T03:00:00Z', registered_count: 32, enabled_count: 31, excluded_count: 9,
  personal_count: 30, total_pages: 3, covered_pages: 1, enabled_pages: 1, coverage_percent: 33.3,
  modules: [
    { module_code: 'procurement', module_name: '采购', state: 'partial', registered_count: 2, enabled_count: 1,
      excluded_count: 0, total_pages: 2, covered_pages: 1, enabled_pages: 1, coverage_percent: 50,
      pages: [{ page_key: 'supplier', page_name: '供应商', route_path: '/purchasing/supplier', registered_count: 2, enabled_count: 1 },
        { page_key: 'missing', page_name: '未覆盖业务页', route_path: '/purchasing/missing', registered_count: 0, enabled_count: 0 }],
      tools: [{ operation: 'procurement.read', summary: '供应商查询', state: 'enabled', write: false, human_decision_required: false },
        { operation: 'procurement.reject', summary: '驳回申请', state: 'disabled', write: true, human_decision_required: true }],
    },
    { module_code: 'energy', module_name: '能源', state: 'not_integrated', registered_count: 0, enabled_count: 0,
      excluded_count: 9, total_pages: 1, covered_pages: 0, enabled_pages: 0, coverage_percent: 0, pages: [], tools: [] },
  ],
}
let cleanup: (() => Promise<void>) | undefined
afterEach(async () => { await cleanup?.(); cleanup = undefined; vi.resetAllMocks() })
async function render() {
  const host = document.createElement('div')
  document.body.appendChild(host)
  const root = createRoot(host)
  cleanup = async () => { await act(async () => root.unmount()); host.remove() }
  await act(async () => { root.render(createElement(AgentModuleCoverageClient)); await new Promise((resolve) => setTimeout(resolve, 60)) })
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 60)) })
}
describe('management module coverage', () => {
  it('shows live coverage, page gaps and human responsibility without repeating role sources', async () => {
    mocks.load.mockResolvedValue(data)
    await render()
    expect(document.body.textContent).toContain('33.3%')
    expect(document.body.textContent).toContain('部分覆盖')
    expect(document.body.textContent).toContain('未接入')
    await act(async () => document.querySelector<HTMLButtonElement>('.ant-table-row-expand-icon')!.click())
    expect(document.body.textContent).toContain('未覆盖业务页')
    const tools = [...document.querySelectorAll<HTMLElement>('[role="tab"]')].find((tab) => tab.textContent === '工具明细')!
    await act(async () => tools.click())
    expect(document.body.textContent).toContain('需人工处理')
    expect(document.body.textContent).not.toContain('管理员：系统管理员')
    expect(mocks.load).toHaveBeenCalledOnce()
  })
  it('shows a request failure and refreshes live data on retry', async () => {
    mocks.load.mockRejectedValue(new Error('需要管理员权限'))
    await render()
    expect(document.body.textContent).toContain('模块接入情况读取失败')
    expect(document.body.textContent).not.toContain('33.3%')
    mocks.load.mockResolvedValue(data)
    const retry = [...document.querySelectorAll<HTMLButtonElement>('button')].find((button) => button.textContent?.replace(/\s/g, '') === '重试')!
    await act(async () => { retry.click(); await new Promise((resolve) => setTimeout(resolve, 60)) })
    expect(document.body.textContent).toContain('33.3%')
    expect(document.body.textContent).not.toContain('模块接入情况读取失败')
  })
})
