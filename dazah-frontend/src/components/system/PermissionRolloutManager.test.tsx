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
  message: { error: vi.fn(), success: vi.fn() },
}))

vi.mock('@/actions/admin', () => ({
  listPagePermissionRollouts: mocks.list,
  previewPagePermissionRollout: mocks.preview,
  publishPagePermissionRollout: mocks.publish,
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

it('shows integration details without the informational banner', async () => {
  mocks.preview.mockResolvedValue(preview())
  await show()

  expect(host.querySelector('.ant-alert-info')).toBeNull()
  expect(document.body.textContent).not.toContain('模块访问和页面权限保存后立即生效')
  expect(document.body.textContent).not.toContain('发布预览')
  expect(document.body.textContent).not.toContain('紧急回退')
  await act(async () => button('查看接入详情').click())
  await act(async () => { await Promise.resolve() })

  expect(document.body.textContent).toContain('权限接入门禁已通过')
  expect(document.body.textContent).toContain('当前无页面访问权限：1')
  expect(document.body.textContent).toContain('确认发布')
})

it('shows current integration gaps without offering publication', async () => {
  mocks.preview.mockResolvedValue(preview(['quality:missing-page']))
  await show()
  await act(async () => button('查看接入详情').click())
  await act(async () => { await Promise.resolve() })

  expect(document.body.textContent).toContain('权限接入门禁未通过')
  expect(document.body.textContent).toContain('quality:missing-page')
  expect(document.body.textContent).not.toContain('确认发布')
})

it('requires a reason and publishes a passing module from the detail panel', async () => {
  mocks.preview.mockResolvedValue(preview())
  mocks.publish.mockResolvedValue({
    ok: true,
    data: { module_code: 'quality', status: 'enforced', version: 3 },
  })
  mocks.list.mockResolvedValueOnce(items).mockResolvedValueOnce([
    { module_code: 'quality', status: 'enforced', version: 3 },
  ] satisfies PermissionModuleRolloutOut[])
  await show()
  await act(async () => button('查看接入详情').click())
  await act(async () => { await Promise.resolve() })

  await act(async () => button('确认发布').click())
  expect(mocks.message.error).toHaveBeenCalledWith('请输入发布原因')
  expect(mocks.publish).not.toHaveBeenCalled()

  const reason = document.querySelector('textarea')
  expect(reason).toBeTruthy()
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set?.call(
      reason,
      '仓储模块接入检查通过',
    )
    reason?.dispatchEvent(new Event('input', { bubbles: true }))
    reason?.dispatchEvent(new Event('change', { bubbles: true }))
  })
  await act(async () => button('确认发布').click())
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) })

  expect(mocks.publish).toHaveBeenCalledWith(preview(), '仓储模块接入检查通过')
  expect(mocks.message.success).toHaveBeenCalledWith('模块权限已发布')
  expect(host.querySelector('.ant-tag-green')?.textContent).toBe('已记录通过')
})

it('keeps the detail open when the publish endpoint rejects the preview', async () => {
  mocks.preview.mockResolvedValue(preview())
  mocks.publish.mockResolvedValue({ ok: false, status: 409, message: '发布预览已过期，请重新预览' })
  await show()
  await act(async () => button('查看接入详情').click())
  await act(async () => { await Promise.resolve() })

  const reason = document.querySelector('textarea')
  expect(reason).toBeTruthy()
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set?.call(
      reason,
      '再次核验模块接入',
    )
    reason?.dispatchEvent(new Event('input', { bubbles: true }))
    reason?.dispatchEvent(new Event('change', { bubbles: true }))
  })
  await act(async () => button('确认发布').click())
  await act(async () => { await Promise.resolve() })

  expect(mocks.message.error).toHaveBeenCalledWith('发布预览已过期，请重新预览')
  expect(mocks.message.success).not.toHaveBeenCalled()
  expect(document.body.textContent).toContain('权限接入门禁已通过')
})

it('reports a list loading failure', async () => {
  mocks.list.mockRejectedValueOnce(new Error('状态读取失败'))
  await show()
  expect(mocks.message.error).toHaveBeenCalledWith('状态读取失败')
})

it('shows each module recorded status with red, yellow and green labels', async () => {
  mocks.list.mockResolvedValue([
    { module_code: 'quality', status: 'legacy', version: 0 },
    { module_code: 'production', status: 'draft', version: 1 },
    { module_code: 'equipment', status: 'enforced', version: 2 },
  ] satisfies PermissionModuleRolloutOut[])
  await show()

  expect(host.textContent).toContain('接入状态')
  const rows = [...host.querySelectorAll('tbody tr')]
  expect(rows).toHaveLength(3)
  for (const [index, color, label] of [
    [0, 'red', '未记录通过'],
    [1, 'yellow', '待核验'],
    [2, 'green', '已记录通过'],
  ] as const) {
    expect(rows[index].querySelector(`.ant-tag-${color}`)?.textContent).toBe(label)
    expect(rows[index].textContent).toContain('查看接入详情')
  }
  expect(mocks.preview).not.toHaveBeenCalled()
})

it('reports a detail loading failure', async () => {
  mocks.preview.mockRejectedValueOnce(new Error('详情不可用'))
  await show()
  await act(async () => button('查看接入详情').click())
  await act(async () => { await Promise.resolve() })
  expect(mocks.message.error).toHaveBeenCalledWith('详情不可用')
})
