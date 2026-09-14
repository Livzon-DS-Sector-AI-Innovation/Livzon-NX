/* @vitest-environment happy-dom */

import { act, createElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type {
  PermissionModuleRolloutOut,
  PermissionModuleRolloutPreviewOut,
} from '@/actions/admin'

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  preview: vi.fn(),
  message: { error: vi.fn() },
}))

vi.mock('@/actions/admin', () => ({
  listPagePermissionRollouts: mocks.list,
  previewPagePermissionRollout: mocks.preview,
}))
vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>()
  return {
    ...actual,
    App: { useApp: () => ({ message: mocks.message }) },
  }
})

import { PermissionRolloutManager } from './PermissionRolloutManager'

const items: PermissionModuleRolloutOut[] = [
  { module_code: 'quality', status: 'draft', version: 2 },
]

const preview = (catalogGaps: string[] = []): PermissionModuleRolloutPreviewOut => ({
  module_code: 'quality',
  current_status: 'draft',
  current_version: 2,
  preview_hash: 'preview-hash',
  page_count: 8,
  user_count: 12,
  users_without_access: 1,
  catalog_gaps: catalogGaps,
})

let root: Root
let host: HTMLDivElement

beforeEach(() => {
  vi.clearAllMocks()
  mocks.list.mockResolvedValue(items)
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

it('states that saved permissions apply immediately and only shows integration details', async () => {
  mocks.preview.mockResolvedValue(preview())
  await show()

  expect(document.body.textContent).toContain('模块访问和页面权限保存后立即生效')
  expect(document.body.textContent).not.toContain('发布预览')
  expect(document.body.textContent).not.toContain('紧急回退')
  await act(async () => button('查看接入详情').click())
  await act(async () => { await Promise.resolve() })

  expect(document.body.textContent).toContain('权限接入门禁已通过')
  expect(document.body.textContent).toContain('当前无页面访问权限：1')
})

it('shows current integration gaps without offering publication', async () => {
  mocks.preview.mockResolvedValue(preview(['quality:missing-page']))
  await show()
  await act(async () => button('查看接入详情').click())
  await act(async () => { await Promise.resolve() })

  expect(document.body.textContent).toContain('权限接入门禁未通过')
  expect(document.body.textContent).toContain('quality:missing-page')
  expect(document.body.textContent).not.toContain('二次确认并发布')
})

it('reports a list loading failure', async () => {
  mocks.list.mockRejectedValueOnce(new Error('状态读取失败'))
  await show()
  expect(mocks.message.error).toHaveBeenCalledWith('状态读取失败')
})

it('reports a detail loading failure', async () => {
  mocks.preview.mockRejectedValueOnce(new Error('详情不可用'))
  await show()
  await act(async () => button('查看接入详情').click())
  await act(async () => { await Promise.resolve() })
  expect(mocks.message.error).toHaveBeenCalledWith('详情不可用')
})
