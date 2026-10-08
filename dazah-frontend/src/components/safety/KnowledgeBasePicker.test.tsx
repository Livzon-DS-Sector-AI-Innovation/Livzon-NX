/* @vitest-environment happy-dom */

import { act, createElement, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  getKnowledgeArticles: vi.fn(),
}))

vi.mock('@/actions/safety', () => ({ getKnowledgeArticles: mocks.getKnowledgeArticles }))

vi.mock('@ant-design/icons', () => {
  const Icon = () => null
  return { SearchOutlined: Icon, FileTextOutlined: Icon }
})

vi.mock('antd', async () => {
  const { createElement } = await import('react')

  type AnyProps = Record<string, unknown> & { children?: ReactNode }
  type ChangeHandler = ((event: { target: { value: string } }) => void) | undefined
  type CheckedHandler = ((event: { target: { checked: boolean } }) => void) | undefined

  const Box = ({ children, onClick }: AnyProps) =>
    createElement('div', { onClick: onClick as never }, children as ReactNode)
  const Text = ({ children }: AnyProps) => createElement('span', null, children as ReactNode)
  // happy-dom 下 React 19 收不到原生 input/change 合成事件，这里用 ref 把 DOM
  // 事件直接接到组件回调，保证受控输入交互真实生效。
  const Input = ({ value, onChange, placeholder, onPressEnter }: AnyProps) =>
    createElement('input', {
      value: (value as string) ?? '',
      placeholder: placeholder as string,
      ref: (node: HTMLInputElement | null) => {
        if (!node) return
        node.onchange = () => (onChange as ChangeHandler)?.({ target: { value: node.value } })
        node.onkeydown = (event: KeyboardEvent) => {
          if (event.key === 'Enter') (onPressEnter as (() => void) | undefined)?.()
        }
      },
    })
  const Checkbox = ({ checked, onChange }: AnyProps) =>
    createElement('input', {
      type: 'checkbox',
      checked: Boolean(checked),
      ref: (node: HTMLInputElement | null) => {
        if (!node) return
        node.onchange = () =>
          (onChange as CheckedHandler)?.({ target: { checked: node.checked } })
      },
    })
  const List = ({ dataSource, renderItem }: AnyProps) =>
    createElement(
      'ul',
      null,
      ((dataSource as unknown[]) ?? []).map((item, index) =>
        createElement('li', { key: index }, (renderItem as (i: unknown) => ReactNode)(item))
      )
    )
  List.Item = Box
  const Modal = ({ open, children, title, okText, onOk, onCancel }: AnyProps) =>
    open === false
      ? null
      : createElement(
          'div',
          null,
          title as ReactNode,
          children as ReactNode,
          createElement('button', { type: 'button', onClick: onOk as never }, okText as ReactNode),
          createElement('button', { type: 'button', onClick: onCancel as never }, '取消')
        )

  return {
    App: { useApp: () => ({ message: mocks.message }) },
    Checkbox,
    Empty: ({ description }: AnyProps) =>
      createElement('div', { 'data-empty': 'true' }, description as ReactNode),
    Input,
    List,
    Modal,
    Space: Box,
    Spin: () => createElement('span', null, 'spin'),
    Tag: Text,
    Typography: { Text },
  }
})

import KnowledgeBasePicker from './KnowledgeBasePicker'

const pickerArticle = (overrides: Record<string, unknown> = {}) => ({
  id: 'doc-1',
  title: '危险化学品安全管理条例',
  regulation_category: '安全类',
  regulation_status: '现行有效',
  ...overrides,
})

let rendered: { root: Root; container: HTMLDivElement } | undefined

const NO_EXCLUSIONS: string[] = []

function renderPicker(overrides: {
  open?: boolean
  onClose?: () => void
  onSelect?: (articles: unknown[]) => void
  excludeIds?: string[]
}) {
  const container = document.createElement('div')
  document.body.append(container)
  const root = createRoot(container)
  act(() => {
    root.render(
      createElement(KnowledgeBasePicker, {
        open: overrides.open ?? true,
        onClose: overrides.onClose ?? (() => undefined),
        onSelect: (overrides.onSelect ?? (() => undefined)) as never,
        // 必须传稳定引用：组件 useCallback 依赖 excludeIds，undefined 会退化成
        // 每次渲染新建空数组，触发无限重新取数
        excludeIds: overrides.excludeIds ?? NO_EXCLUSIONS,
      })
    )
  })
  return { root, container }
}

async function settle() {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
    await new Promise((resolve) => setTimeout(resolve, 0))
  })
}

function findButton(container: HTMLElement, text: string): HTMLButtonElement | undefined {
  return Array.from(container.querySelectorAll('button')).find((button) =>
    button.textContent?.includes(text)
  ) as HTMLButtonElement | undefined
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.getKnowledgeArticles.mockResolvedValue({ code: 200, data: [pickerArticle()] })
})

afterEach(() => {
  if (rendered) {
    act(() => rendered?.root.unmount())
    rendered.container.remove()
    rendered = undefined
  }
})

describe('KnowledgeBasePicker', () => {
  it('fetches regulation documents when opened and renders category/status tags', async () => {
    rendered = renderPicker({})
    await settle()

    expect(mocks.getKnowledgeArticles).toHaveBeenCalledWith({ page_size: 50, keyword: undefined })
    const markup = rendered.container.innerHTML
    expect(markup).toContain('危险化学品安全管理条例')
    expect(markup).toContain('安全类')
    expect(markup).toContain('现行有效')
  })

  it('filters out already selected articles and shows the empty state', async () => {
    rendered = renderPicker({ excludeIds: ['doc-1'] })
    await settle()

    expect(rendered.container.innerHTML).toContain('暂无可选的法规文档')
  })

  it('reports a fetch failure', async () => {
    mocks.getKnowledgeArticles.mockRejectedValueOnce(new Error('boom'))
    rendered = renderPicker({})
    await settle()

    expect(mocks.message.error).toHaveBeenCalledWith('获取知识库文章失败')
  })

  it('searches by keyword through the input and Enter key', async () => {
    rendered = renderPicker({})
    await settle()
    mocks.getKnowledgeArticles.mockClear()

    const input = rendered.container.querySelector('input') as HTMLInputElement
    act(() => {
      input.value = '条例'
      input.dispatchEvent(new Event('change', { bubbles: true }))
    })
    await settle()
    act(() => {
      input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
    })
    await settle()

    expect(mocks.getKnowledgeArticles).toHaveBeenCalledWith({ page_size: 50, keyword: '条例' })
  })

  it('warns when confirming without a selection', async () => {
    const onSelect = vi.fn()
    rendered = renderPicker({ onSelect })
    await settle()

    act(() => findButton(rendered!.container, '确认选择')?.click())
    await settle()

    expect(mocks.message.warning).toHaveBeenCalledWith('请至少选择一篇文章')
    expect(onSelect).not.toHaveBeenCalled()
  })

  it('selects through the checkbox and list row, then confirms', async () => {
    const onClose = vi.fn()
    const onSelect = vi.fn()
    rendered = renderPicker({ onClose, onSelect })
    await settle()

    const checkbox = rendered.container.querySelector('input[type="checkbox"]') as HTMLInputElement
    act(() => {
      checkbox.checked = true
      checkbox.dispatchEvent(new Event('change', { bubbles: true }))
    })
    await settle()
    expect(rendered.container.innerHTML).toContain('确认选择 (1 篇)')

    // 行点击再次切换为未选中，随后重新选中（onClick 挂在 List.Item 上）
    const row = rendered!.container.querySelector('li > div') as HTMLElement
    act(() => row.click())
    await settle()
    expect(rendered.container.innerHTML).toContain('确认选择 (0 篇)')
    act(() => row.click())
    await settle()

    act(() => findButton(rendered!.container, '确认选择')?.click())
    await settle()
    expect(onSelect).toHaveBeenCalledWith([expect.objectContaining({ id: 'doc-1' })])
    expect(onClose).toHaveBeenCalled()
  })

  it('does not fetch while closed and clears state on close', async () => {
    rendered = renderPicker({ open: false })
    await settle()

    expect(mocks.getKnowledgeArticles).not.toHaveBeenCalled()

    act(() =>
      rendered?.root.render(
        createElement(KnowledgeBasePicker, {
          open: true,
          onClose: () => undefined,
          onSelect: () => undefined,
          excludeIds: NO_EXCLUSIONS,
        })
      )
    )
    await settle()
    expect(mocks.getKnowledgeArticles).toHaveBeenCalledTimes(1)

    act(() =>
      rendered?.root.render(
        createElement(KnowledgeBasePicker, {
          open: false,
          onClose: () => undefined,
          onSelect: () => undefined,
          excludeIds: NO_EXCLUSIONS,
        })
      )
    )
    await settle()
    expect(rendered.container.querySelectorAll('input[type="checkbox"]').length).toBe(0)
  })
})