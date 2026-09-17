/* @vitest-environment happy-dom */

import { act, createElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { PermissionModuleIntegrationOut, PermissionModuleRolloutPreviewOut } from '@/actions/admin'

const mocks = vi.hoisted(() => ({
  list: vi.fn(), preview: vi.fn(), message: { error: vi.fn() },
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
})
async function show() {
  await act(async () => root.render(createElement(PermissionRolloutManager)))
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) })
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
  const rows = [...host.querySelectorAll('tbody tr')]
  expect(rows).toHaveLength(1)
  expect(rows[0].textContent).toContain('质量管理')
  expect(host.textContent).not.toContain('产品管理')
  expect(host.textContent).not.toContain('申报资料撰写')
  expect(host.textContent).not.toContain('环保管理')
  expect(host.textContent).not.toContain('法规追踪')
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
