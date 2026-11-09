/* @vitest-environment happy-dom */

import { act, createElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { ConfigProvider, theme } from 'antd'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { PermissionModuleIntegrationOut, PermissionModuleRolloutPreviewOut } from '@/actions/admin'

const mocks = vi.hoisted(() => ({
  list: vi.fn(), preview: vi.fn(), message: { error: vi.fn(), warning: vi.fn() },
}))
vi.mock('@/actions/admin', () => ({
  listPagePermissionRollouts: mocks.list,
  previewPagePermissionRollout: mocks.preview,
}))
vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>()
  return { ...actual, App: { useApp: () => ({ message: mocks.message }) } }
})

import { PermissionRolloutManager } from './PermissionRolloutManager'

const item = (gaps: string[] = []): PermissionModuleIntegrationOut => ({
  module_code: 'quality', passed: gaps.length === 0, catalog_gaps: gaps,
})
const preview = (gaps: string[] = []): PermissionModuleRolloutPreviewOut => ({
  module_code: 'quality', current_status: 'draft', current_version: 0,
  preview_hash: 'preview-hash', page_count: 8, user_count: 12,
  users_without_access: 1, catalog_gaps: gaps,
})
let root: Root
let host: HTMLDivElement
beforeEach(() => {
  vi.clearAllMocks()
  mocks.list.mockResolvedValue([item()])
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
})
afterEach(async () => {
  await act(async () => root.unmount())
  host.remove()
  vi.useRealTimers()
  vi.restoreAllMocks()
})
async function show() {
  await act(async () => root.render(createElement(PermissionRolloutManager)))
  await act(async () => {
    if (vi.isFakeTimers()) await vi.advanceTimersByTimeAsync(0)
    else await new Promise((resolve) => setTimeout(resolve, 0))
  })
}
function button(label: string) {
  const found = [...document.querySelectorAll('button')].find(
    (node) => node.textContent?.replace(/\s/g, '') === label,
  )
  expect(found, label).toBeTruthy()
  return found!
}

it('shows automatic current result and no manual publication action', async () => {
  mocks.preview.mockResolvedValue(preview())
  await show()
  expect(host.textContent).toContain('自动检查通过')
  await act(async () => button('查看接入详情').click())
  await act(async () => { await Promise.resolve() })
  expect(document.body.textContent).toContain('当前接入检查通过')
  const rules = [...document.querySelectorAll<HTMLButtonElement>('[data-platform-notice] button')]
    .find((button) => button.textContent?.includes('了解访问规则'))!
  await act(async () => rules.click())
  expect(document.body.textContent).toContain('实际请求仍由后端逐次鉴权')
  expect(document.body.textContent).not.toContain('确认发布')
})

it('only lists modules configured in the top navigation', async () => {
  mocks.list.mockResolvedValueOnce([
    item(),
    { module_code: 'product', passed: false, catalog_gaps: ['未登记有效菜单页面'] },
    { module_code: 'dossier_writer', passed: false, catalog_gaps: ['未登记有效菜单页面'] },
    { module_code: 'environment', passed: false, catalog_gaps: ['未登记有效菜单页面'] },
    { module_code: 'regulatory_tracker', passed: false, catalog_gaps: ['未登记有效菜单页面'] },
  ] satisfies PermissionModuleIntegrationOut[])
  await show()
  const rows = [...host.querySelectorAll('tbody tr[data-row-key]')]
  expect(rows).toHaveLength(1)
  expect(rows[0].textContent).toContain('质量管理')
  expect(host.textContent).not.toContain('产品管理')
  expect(host.textContent).not.toContain('申报资料撰写')
  expect(host.textContent).not.toContain('环保管理')
  expect(host.textContent).not.toContain('法规追踪')
})

it('handles omitted list gaps without changing the server check result', async () => {
  mocks.list.mockResolvedValue([
    { module_code: 'quality', passed: false },
  ] satisfies PermissionModuleIntegrationOut[])
  await show()
  expect(host.textContent).toContain('接入有缺口')
  expect(host.querySelector('[data-row-key="quality"] td:nth-child(3)')?.textContent).toBe('0')
  await act(async () => button('重新检查').click())
  expect(mocks.list).toHaveBeenCalledTimes(2)
  expect(host.textContent).toContain('接入有缺口')
  expect(mocks.message.error).not.toHaveBeenCalled()
  expect(mocks.message.warning).not.toHaveBeenCalled()
})

it('uses the schema default when detail gaps are omitted', async () => {
  const withoutGaps = preview()
  delete withoutGaps.catalog_gaps
  mocks.list.mockResolvedValue([item(['接口｜GET /api/v1/quality/old：未登记'])])
  mocks.preview.mockResolvedValue(withoutGaps)
  await show()
  await act(async () => button('查看接入详情').click())
  expect(document.body.textContent).toContain('当前接入检查通过')
  expect(document.body.textContent).not.toContain('GET /api/v1/quality/old')
  expect(host.textContent).toContain('自动检查通过')
  expect(host.querySelector('[data-row-key="quality"] td:nth-child(3)')?.textContent).toBe('0')
  expect(mocks.message.error).not.toHaveBeenCalled()
})

it('refreshes open details when the next preview omits gaps', async () => {
  vi.useFakeTimers()
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible')
  const gaps = ['接口｜GET /api/v1/quality/old：未登记']
  const withoutGaps = preview()
  delete withoutGaps.catalog_gaps
  mocks.list.mockResolvedValue([item(gaps)])
  mocks.preview.mockResolvedValueOnce(preview(gaps)).mockResolvedValue(withoutGaps)
  await show()
  await act(async () => button('查看接入详情').click())
  expect(document.body.textContent).toContain('当前接入检查未通过')
  await act(async () => button('重新检查').click())
  expect(mocks.preview).toHaveBeenCalledTimes(2)
  expect(document.body.textContent).toContain('当前接入检查通过')
  expect(document.body.textContent).not.toContain('GET /api/v1/quality/old')
  expect(host.textContent).toContain('自动检查通过')
  expect(host.querySelector('[data-row-key="quality"] td:nth-child(3)')?.textContent).toBe('0')
  expect(mocks.message.error).not.toHaveBeenCalled()
  expect(mocks.message.warning).not.toHaveBeenCalled()
})

it('rechecks stale module results and displays live gaps', async () => {
  mocks.preview.mockResolvedValue(preview(['接口绑定缺失']))
  mocks.list.mockResolvedValueOnce([item()]).mockResolvedValueOnce([item(['接口绑定缺失'])])
  await show()
  await act(async () => button('查看接入详情').click())
  await act(async () => { await Promise.resolve() })
  expect(document.body.textContent).toContain('当前接入检查未通过')
  expect(host.textContent).toContain('接入有缺口')
  await act(async () => button('重新检查').click())
  await act(async () => { await Promise.resolve() })
  expect(mocks.list).toHaveBeenCalledTimes(2)
})

it('reports loading failures', async () => {
  mocks.list.mockRejectedValueOnce(new Error('状态读取失败'))
  await show()
  expect(mocks.message.error).toHaveBeenCalledWith('状态读取失败')
  expect(host.textContent).toContain('无法获取当前检查结果')
  mocks.list.mockResolvedValueOnce([item()])
  await act(async () => button('重新检查').click())
  await act(async () => { await Promise.resolve() })
  mocks.preview.mockRejectedValueOnce(new Error('详情不可用'))
  await act(async () => button('查看接入详情').click())
  await act(async () => { await Promise.resolve() })
  expect(mocks.message.error).toHaveBeenCalledWith('详情不可用')
})

it('counts every interface and shows categorized details with exact targets', async () => {
  const gaps = [
    ...Array.from({ length: 10 }, (_, index) => `接口｜GET /api/v1/quality/new-${index}：未登记`),
    '页面｜/quality/new-report：未登记',
    'Livzon 工具｜分析（analysis））：未登记',
  ]
  mocks.list.mockResolvedValue([item(gaps)])
  mocks.preview.mockResolvedValue(preview(gaps))
  await show()
  expect(host.querySelector('[data-row-key="quality"] td:nth-child(3)')?.textContent).toBe('12')
  expect(host.textContent).toContain('最近检查：')
  await act(async () => button('查看接入详情').click())
  expect(document.body.textContent).toContain('接口（10）')
  expect(document.body.textContent).toContain('页面（1）')
  expect(document.body.textContent).toContain('Livzon 工具（1）')
  expect(document.body.textContent).toContain('GET /api/v1/quality/new-9')
})

it('does not poll while idle and checks manually without repeating known object warnings', async () => {
  vi.useFakeTimers()
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible')
  await show()
  mocks.list.mockResolvedValue([item(['接口｜GET /api/v1/quality/new：未登记'])])
  await act(async () => { await vi.advanceTimersByTimeAsync(5 * 60_000) })
  expect(mocks.list).toHaveBeenCalledTimes(1)
  expect(host.querySelector('[data-row-key="quality"] td:nth-child(3)')?.textContent).toBe('0')
  await act(async () => button('重新检查').click())
  expect(mocks.list).toHaveBeenCalledTimes(2)
  expect(host.querySelector('[data-row-key="quality"] td:nth-child(3)')?.textContent).toBe('1')
  expect(mocks.message.warning).toHaveBeenCalledTimes(1)
  mocks.list.mockResolvedValue([item(['接口｜GET /api/v1/quality/new：范围未适配'])])
  await act(async () => button('重新检查').click())
  expect(mocks.list).toHaveBeenCalledTimes(3)
  expect(mocks.message.warning).toHaveBeenCalledTimes(1)
})

it('does not refresh on window focus or visibility changes', async () => {
  vi.useFakeTimers()
  const visibility = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden')
  await show()
  await act(async () => window.dispatchEvent(new Event('focus')))
  await act(async () => { await vi.advanceTimersByTimeAsync(60_000) })
  expect(mocks.list).toHaveBeenCalledTimes(1)
  visibility.mockReturnValue('visible')
  await act(async () => document.dispatchEvent(new Event('visibilitychange')))
  await act(async () => window.dispatchEvent(new Event('focus')))
  expect(mocks.list).toHaveBeenCalledTimes(1)
})

it('checks again when the permission check page is entered again', async () => {
  await show()
  expect(mocks.list).toHaveBeenCalledTimes(1)
  await act(async () => root.render(null))
  mocks.list.mockResolvedValue([item(['接口｜GET /api/v1/quality/new：未登记'])])
  await show()
  expect(mocks.list).toHaveBeenCalledTimes(2)
  expect(host.querySelector('[data-row-key="quality"] td:nth-child(3)')?.textContent).toBe('1')
})

it('prevents duplicate manual requests and stops checking after unmount', async () => {
  vi.useFakeTimers()
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible')
  await show()
  let finish: (value: PermissionModuleIntegrationOut[]) => void = () => {}
  mocks.list.mockReturnValueOnce(new Promise<PermissionModuleIntegrationOut[]>((resolve) => { finish = resolve }))
  await act(async () => button('重新检查').click())
  await act(async () => {
    button('重新检查').click()
    window.dispatchEvent(new Event('focus'))
    document.dispatchEvent(new Event('visibilitychange'))
    await vi.advanceTimersByTimeAsync(60_000)
  })
  expect(mocks.list).toHaveBeenCalledTimes(2)
  await act(async () => finish([item()]))
  await act(async () => root.unmount())
  await act(async () => {
    window.dispatchEvent(new Event('focus'))
    await vi.advanceTimersByTimeAsync(60_000)
  })
  expect(mocks.list).toHaveBeenCalledTimes(2)
})

it('clears stale passing results on manual failure and recovers on the next manual check', async () => {
  vi.useFakeTimers()
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible')
  await show()
  mocks.list.mockRejectedValueOnce(new Error('检查服务暂不可用'))
  await act(async () => button('重新检查').click())
  expect(host.textContent).not.toContain('自动检查通过')
  expect(host.textContent).toContain('检查服务暂不可用')
  expect(host.textContent).toContain('尚未完成检查')
  expect(mocks.message.error).toHaveBeenCalledWith('检查服务暂不可用')
  await act(async () => button('重新检查').click())
  expect(host.textContent).toContain('自动检查通过')
  expect(host.textContent).not.toContain('检查服务暂不可用')
})

it('refreshes an open detail view together with the list', async () => {
  vi.useFakeTimers()
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible')
  mocks.preview.mockResolvedValueOnce(preview())
  await show()
  await act(async () => button('查看接入详情').click())
  mocks.preview.mockResolvedValue(preview(['接口｜GET /api/v1/quality/new：未登记']))
  await act(async () => button('重新检查').click())
  expect(host.querySelector('[data-row-key="quality"] td:nth-child(3)')?.textContent).toBe('1')
  expect(document.body.textContent).toContain('接口（1）')
  expect(document.body.textContent).toContain('GET /api/v1/quality/new')
})

it.each(['light', 'dark'] as const)('renders gap counts and details under the %s theme', async (mode) => {
  const gaps = ['接口｜GET /api/v1/quality/new：未登记']
  mocks.list.mockResolvedValue([item(gaps)])
  mocks.preview.mockResolvedValue(preview(gaps))
  await act(async () => root.render(createElement(ConfigProvider, {
    theme: { algorithm: mode === 'dark' ? theme.darkAlgorithm : theme.defaultAlgorithm },
  }, createElement(PermissionRolloutManager))))
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) })
  expect(host.textContent).toContain('接入有缺口')
  expect(host.querySelector('[data-row-key="quality"] td:nth-child(3)')?.textContent).toBe('1')
  await act(async () => button('查看接入详情').click())
  expect(document.body.textContent).toContain('接口（1）')
  expect(document.body.querySelector('[data-platform-notice="error"]')).not.toBeNull()
})

it('does not reopen a detail view closed while a refresh is pending', async () => {
  vi.useFakeTimers()
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible')
  mocks.preview.mockResolvedValueOnce(preview())
  await show()
  await act(async () => button('查看接入详情').click())
  let finish: (value: PermissionModuleRolloutPreviewOut) => void = () => {}
  mocks.preview.mockReturnValueOnce(new Promise<PermissionModuleRolloutPreviewOut>((resolve) => { finish = resolve }))
  await act(async () => button('重新检查').click())
  await act(async () => button('关闭').click())
  await act(async () => finish(preview(['接口｜GET /new：未登记'])))
  await act(async () => { await vi.advanceTimersByTimeAsync(500) })
  expect(host.querySelector('[data-row-key="quality"] td:nth-child(3)')?.textContent).toBe('1')
  expect(document.body.textContent).not.toContain('GET /new')
})
