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
  publish: vi.fn(),
  rollback: vi.fn(),
  message: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

vi.mock('@/actions/admin', () => ({
  listPagePermissionRollouts: mocks.list,
  previewPagePermissionRollout: mocks.preview,
  publishPagePermissionRollout: mocks.publish,
  rollbackPagePermissionRollout: mocks.rollback,
}))
vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>()
  return {
    ...actual,
    App: {
      useApp: () => ({ message: mocks.message, modal: { confirm: vi.fn() } }),
    },
  }
})

import { PermissionRolloutManager } from './PermissionRolloutManager'

const items: PermissionModuleRolloutOut[] = [
  { module_code: 'hr', status: 'legacy', version: 0 },
  { module_code: 'quality', status: 'draft', version: 2, last_reason: '待发布' },
  { module_code: 'production', status: 'enforced', version: 3, last_reason: '已上线' },
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

function setTextInput(selector: string, value: string) {
  const input = document.querySelector<HTMLInputElement | HTMLTextAreaElement>(selector)
  expect(input).toBeTruthy()
  Object.getOwnPropertyDescriptor(Object.getPrototypeOf(input!), 'value')?.set?.call(input, value)
  input!.dispatchEvent(new Event('input', { bubbles: true }))
}

it('loads rollout states, previews a module, and publishes after an audit reason', async () => {
  const nextPreview = preview()
  mocks.preview.mockResolvedValue(nextPreview)
  mocks.publish.mockResolvedValue({ ok: true, data: items[1] })
  await show()

  expect(document.body.textContent).toContain('旧规则')
  expect(document.body.textContent).toContain('草稿')
  expect(document.body.textContent).toContain('已发布')
  await act(async () => button('发布预览').click())
  await act(async () => { await Promise.resolve() })
  expect(document.body.textContent).toContain('有效页面：8；影响用户：12；发布后无页面访问权限：1')

  await act(async () => button('二次确认并发布').click())
  expect(mocks.message.warning).toHaveBeenCalledWith('请填写发布原因')

  await act(async () => setTextInput('textarea[placeholder="填写本次发布原因"]', '正式发布'))
  await act(async () => button('二次确认并发布').click())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) })
  expect(mocks.publish).toHaveBeenCalledWith(nextPreview, '正式发布')
  expect(mocks.message.success).toHaveBeenCalledWith('模块页面权限已发布')
})

it('reports an initial load failure', async () => {
  mocks.list.mockRejectedValueOnce(new Error('状态读取失败'))
  await show()
  expect(mocks.message.error).toHaveBeenCalledWith('状态读取失败')
})

it('reports a preview failure', async () => {
  mocks.preview.mockRejectedValueOnce(new Error('预览不可用'))
  await show()
  await act(async () => button('发布预览').click())
  await act(async () => { await Promise.resolve() })
  expect(mocks.message.error).toHaveBeenCalledWith('预览不可用')
})

it('reports a publish failure', async () => {
  await show()
  mocks.preview.mockResolvedValueOnce(preview())
  await act(async () => button('发布预览').click())
  await act(async () => { await Promise.resolve() })
  await act(async () => setTextInput('textarea[placeholder="填写本次发布原因"]', '发布失败测试'))
  mocks.publish.mockResolvedValueOnce({ ok: false, message: '发布门禁未通过' })
  await act(async () => button('二次确认并发布').click())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) })
  expect(mocks.message.error).toHaveBeenCalledWith('发布门禁未通过')
})

it('reports a rollback failure after the emergency confirmation', async () => {
  await show()
  await act(async () => setTextInput('input[placeholder="填写发布或紧急回退原因"]', '回退失败测试'))
  await act(async () => button('紧急回退').click())
  await act(async () => button('OK').click())
  mocks.rollback.mockResolvedValueOnce({ ok: false, message: '回退版本冲突' })
  await act(async () => button('紧急回退').click())
  await act(async () => button('OK').click())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) })
  expect(mocks.rollback).toHaveBeenCalledWith('production', 3, '回退失败测试')
  expect(mocks.message.error).toHaveBeenCalledWith('回退版本冲突')
})

it('requires a rollback reason and blocks publish when the catalog has gaps', async () => {
  mocks.preview.mockResolvedValueOnce(preview(['quality:missing-page']))
  await show()
  await act(async () => button('紧急回退').click())
  await act(async () => button('OK').click())
  expect(mocks.message.warning).toHaveBeenCalledWith('请先填写紧急回退原因')

  await act(async () => button('发布预览').click())
  await act(async () => { await Promise.resolve() })
  expect(document.body.textContent).toContain('发布门禁未通过')
  expect(document.body.textContent).toContain('quality:missing-page')
  expect(button('二次确认并发布').hasAttribute('disabled')).toBe(true)
})
