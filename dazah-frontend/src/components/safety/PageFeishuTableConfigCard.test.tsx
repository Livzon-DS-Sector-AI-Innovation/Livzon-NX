/* @vitest-environment happy-dom */

import { act, createElement, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  getSafetyPageFeishuConfigs: vi.fn(),
  resolveSafetyPageFeishuUrl: vi.fn(),
  saveSafetyPageFeishuConfig: vi.fn(),
  syncSafetyPageFeishuConfig: vi.fn(),
  testSafetyPageFeishuConfig: vi.fn(),
}))

vi.mock('@/actions/safety', () => ({
  getSafetyPageFeishuConfigs: mocks.getSafetyPageFeishuConfigs,
  resolveSafetyPageFeishuUrl: mocks.resolveSafetyPageFeishuUrl,
  saveSafetyPageFeishuConfig: mocks.saveSafetyPageFeishuConfig,
  syncSafetyPageFeishuConfig: mocks.syncSafetyPageFeishuConfig,
  testSafetyPageFeishuConfig: mocks.testSafetyPageFeishuConfig,
}))

vi.mock('@/components/shared/PlatformNotice', async () => {
  const { createElement } = await import('react')
  return {
    default: ({ title, description }: { title?: ReactNode; description?: ReactNode }) =>
      createElement(
        'div',
        { 'data-notice': 'true' },
        title as ReactNode,
        createElement('span', { 'data-description': 'true' }, description as ReactNode)
      ),
  }
})

vi.mock('@ant-design/icons', () => {
  const Icon = () => null
  return { ApiOutlined: Icon, LinkOutlined: Icon, SaveOutlined: Icon, SyncOutlined: Icon }
})

vi.mock('antd', async () => {
  const { createElement } = await import('react')

  type AnyProps = Record<string, unknown> & { children?: ReactNode }
  type ChangeHandler = ((event: { target: { value: string } }) => void) | undefined

  const Box = ({ children, title, extra }: AnyProps) =>
    createElement('div', null, title as ReactNode, extra as ReactNode, children as ReactNode)
  const Text = ({ children }: AnyProps) => createElement('span', null, children as ReactNode)
  const Button = ({ children, onClick, disabled }: AnyProps) =>
    createElement(
      'button',
      { type: 'button', disabled: Boolean(disabled), onClick: onClick as never },
      children as ReactNode
    )
  // happy-dom 下 React 19 收不到原生 input/change 合成事件，用 ref 接线
  const textInput = (props: AnyProps) =>
    createElement('input', {
      value: (props.value as string) ?? '',
      placeholder: props.placeholder as string,
      ref: (node: HTMLInputElement | null) => {
        if (!node) return
        node.onchange = () =>
          (props.onChange as ChangeHandler)?.({ target: { value: node.value } })
        node.onkeydown = (event: KeyboardEvent) => {
          if (event.key === 'Enter') (props.onPressEnter as (() => void) | undefined)?.()
        }
      },
    })
  const Input = Object.assign(textInput, { TextArea: textInput })
  // 多选 Select 渲染为可交互 checkbox 列表（单选 Select 维持原占位渲染）
  const Select = (props: AnyProps) => {
    if (props.mode === 'multiple') {
      const selected = (props.value as string[] | undefined) ?? []
      const options =
        (props.options as { value: string; label: string }[] | undefined) ?? []
      return createElement(
        'div',
        { 'data-multiselect': 'true' },
        ...options.map((option) =>
          createElement('input', {
            key: option.value,
            type: 'checkbox',
            'data-option-value': option.value,
            'data-option-label': option.label,
            checked: selected.includes(option.value),
            ref: (node: HTMLInputElement | null) => {
              if (!node) return
              node.onchange = () => {
                const next = node.checked
                  ? [...new Set([...selected, option.value])]
                  : selected.filter((item) => item !== option.value)
                ;(props.onChange as ((value: string[]) => void) | undefined)?.(next)
              }
            },
          })
        )
      )
    }
    return Box(props)
  }
  const Switch = ({ checked, onChange }: AnyProps) =>
    createElement('input', {
      type: 'checkbox',
      checked: Boolean(checked),
      ref: (node: HTMLInputElement | null) => {
        if (!node) return
        node.onchange = () =>
          (onChange as ((checked: boolean) => void) | undefined)?.(node.checked)
      },
    })

  return {
    App: { useApp: () => ({ message: mocks.message }) },
    Button,
    Card: Box,
    Input,
    Select,
    Space: Object.assign(Box, { Compact: Box }),
    Switch,
    Tag: Text,
    Typography: { Text, Paragraph: Text },
  }
})

import {
  formatWorkshopAliasText,
  parseWorkshopAliasText,
  default as PageFeishuTableConfigCard,
} from './PageFeishuTableConfigCard'

const configItem = {
  page_key: 'safety:risk-hazard:hazard-inspection:hazard-duty',
  page_name: '24小时值班隐患',
  route_path: '/safety/hazard-duty',
  app_token: 'bascnOld',
  table_id: 'tblOld',
  view_id: 'vewOld',
  hidden_field_names: ['公式列'],
  sub_tables: [
    { table_id: 'tblSubOld', tab_name: '2025年公司级检查', hidden_field_names: ['父记录'] },
  ],
  workshop_aliases: { DR提炼: '201二车间（DR）' },
  is_enabled: true,
  is_mirrored: true,
  last_synced_at: '2026-10-13T02:00:00.000Z',
  last_sync_status: 'success',
  last_sync_error: null,
  last_sync_record_count: 20,
  last_test_status: 'success',
  last_tested_at: '2026-10-10T02:00:00.000Z',
  last_test_error: null,
  last_test_field_count: 6,
  last_test_record_count: 20,
}

let rendered: { root: Root; container: HTMLDivElement } | undefined

function renderCard() {
  const container = document.createElement('div')
  document.body.append(container)
  const root = createRoot(container)
  act(() => {
    root.render(createElement(PageFeishuTableConfigCard))
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

function setInput(container: HTMLElement, placeholderPrefix: string, value: string) {
  const input = Array.from(container.querySelectorAll('input')).find(
    (node) => node.placeholder && node.placeholder.startsWith(placeholderPrefix)
  ) as HTMLInputElement | undefined
  if (!input) return
  input.value = value
  input.dispatchEvent(new Event('change', { bubbles: true }))
}

function findSubTableOption(container: HTMLElement, optionValue: string): HTMLInputElement {
  const checkbox = Array.from(
    container.querySelectorAll('input[type="checkbox"][data-option-value]')
  ).find((node) => (node as HTMLInputElement).dataset.optionValue === optionValue) as
    | HTMLInputElement
    | undefined
  if (!checkbox) throw new Error(`未找到页签子表选项 ${optionValue}`)
  return checkbox
}

function toggleSubTable(container: HTMLElement, optionValue: string, checked: boolean) {
  const checkbox = findSubTableOption(container, optionValue)
  act(() => {
    checkbox.checked = checked
    checkbox.dispatchEvent(new Event('change', { bubbles: true }))
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.getSafetyPageFeishuConfigs.mockResolvedValue({
    code: 200,
    data: { items: [configItem] },
  })
  mocks.saveSafetyPageFeishuConfig.mockResolvedValue({
    code: 200,
    data: configItem,
  })
  mocks.testSafetyPageFeishuConfig.mockResolvedValue({
    code: 200,
    data: { success: true, message: '绑定正常', fields: [{ name: '记录编号' }] },
  })
  mocks.syncSafetyPageFeishuConfig.mockResolvedValue({
    code: 200,
    data: { ...configItem, last_sync_record_count: 21 },
  })
  mocks.resolveSafetyPageFeishuUrl.mockResolvedValue({
    code: 200,
    data: {
      app_token: 'bascnNew',
      table_id: 'tblNew',
      view_id: 'vewNew',
      is_wiki: false,
      tables: [{ table_id: 'tblNew', table_name: '新表' }],
    },
  })
})

afterEach(() => {
  if (rendered) {
    act(() => rendered?.root.unmount())
    rendered.container.remove()
    rendered = undefined
  }
})

describe('parseWorkshopAliasText', () => {
  it('parses full-width and half-width separators, skipping junk lines', () => {
    expect(
      parseWorkshopAliasText('DR提炼=201二车间（DR）\n包装＝301包装车间\n\n只有别名\n')
    ).toEqual({ DR提炼: '201二车间（DR）', 包装: '301包装车间' })
  })

  it('formats aliases back to lines', () => {
    expect(formatWorkshopAliasText({ A: 'B', C: 'D' })).toBe('A=B\nC=D')
    expect(formatWorkshopAliasText(null as never)).toBe('')
  })
})

describe('PageFeishuTableConfigCard', () => {
  it('renders configured pages', async () => {
    rendered = renderCard()
    await settle()

    expect(rendered.container.innerHTML).toContain('24小时值班隐患')
    expect(rendered.container.innerHTML).toContain('绑定正常')
    expect(rendered.container.innerHTML).toContain('字段 6 个 / 记录 20 条')
  })

  it('falls back to the empty notice without configured pages', async () => {
    mocks.getSafetyPageFeishuConfigs.mockResolvedValue({
      code: 200,
      data: { items: [] },
    })
    rendered = renderCard()
    await settle()

    expect(rendered.container.innerHTML).toContain('暂无可配置的镜像页')
  })

  it('warns when saving without app token or table id', async () => {
    rendered = renderCard()
    await settle()

    // 清空两个必填输入再保存（用占位符前缀精确匹配，避免误中链接输入框）
    setInput(rendered.container, '多维表格 app_token', '')
    setInput(rendered.container, '数据表 table_id', '')
    await settle()

    act(() => findButton(rendered!.container, '保存')?.click())
    await settle()

    expect(mocks.message.warning).toHaveBeenCalledWith('请填写 App Token 与 Table ID')
    expect(mocks.saveSafetyPageFeishuConfig).not.toHaveBeenCalled()
  })

  it('saves the binding with parsed aliases and switch state', async () => {
    rendered = renderCard()
    await settle()

    setInput(rendered.container, '多维表格 app_token', '  bascnSaved  ')
    const aliasesInput = Array.from(
      rendered.container.querySelectorAll('input')
    ).find((node) => (node as HTMLInputElement).value?.includes('DR提炼'))
    if (!aliasesInput) throw new Error('未找到别名输入框')
    act(() => {
      aliasesInput.value = '新别名=一车间'
      aliasesInput.dispatchEvent(new Event('change', { bubbles: true }))
    })
    const switchInput = rendered.container.querySelector(
      'input[type="checkbox"]'
    ) as HTMLInputElement
    act(() => {
      switchInput.checked = false
      switchInput.dispatchEvent(new Event('change', { bubbles: true }))
    })
    await settle()

    act(() => findButton(rendered!.container, '保存')?.click())
    await settle()

    expect(mocks.saveSafetyPageFeishuConfig).toHaveBeenCalledWith(
      'safety:risk-hazard:hazard-inspection:hazard-duty',
      expect.objectContaining({
        app_token: 'bascnSaved',
        table_id: 'tblOld',
        workshop_aliases: { 新别名: '一车间' },
        is_enabled: false,
        is_mirrored: true,
      })
    )
    expect(mocks.message.success).toHaveBeenCalledWith('页面数据表绑定已保存')
  })

  it('syncs the mirror on demand and reports the record count', async () => {
    rendered = renderCard()
    await settle()

    act(() => findButton(rendered!.container, '立即同步')?.click())
    await settle()

    expect(mocks.syncSafetyPageFeishuConfig).toHaveBeenCalledWith(
      'safety:risk-hazard:hazard-inspection:hazard-duty'
    )
    expect(mocks.message.success).toHaveBeenCalledWith('镜像同步完成（21 条记录）')
  })

  it('resolves a pasted link and reports failures', async () => {
    rendered = renderCard()
    await settle()

    // 空链接 → 提示
    act(() => findButton(rendered!.container, '解析')?.click())
    await settle()
    expect(mocks.message.warning).toHaveBeenCalledWith('请先粘贴多维表格链接')

    setInput(
      rendered.container,
      '粘贴多维表格链接',
      'https://example.feishu.cn/base/bascnNew?table=tblNew&view=vewNew'
    )
    await settle()
    act(() => findButton(rendered!.container, '解析')?.click())
    await settle()

    expect(mocks.resolveSafetyPageFeishuUrl).toHaveBeenCalledWith(
      'https://example.feishu.cn/base/bascnNew?table=tblNew&view=vewNew'
    )
    expect(mocks.message.success).toHaveBeenCalledWith(
      '已解析，找到 1 个子表，请确认 Table ID'
    )
    // 解析结果回填 App Token 输入框
    const tokenInput = Array.from(rendered!.container.querySelectorAll('input')).find(
      (node) => node.placeholder?.startsWith('多维表格 app_token')
    ) as HTMLInputElement
    expect(tokenInput.value).toBe('bascnNew')

    // 解析失败分支
    mocks.resolveSafetyPageFeishuUrl.mockResolvedValueOnce({
      code: 500,
      message: '链接无法解析',
    })
    act(() => findButton(rendered!.container, '解析')?.click())
    await settle()
    expect(mocks.message.error).toHaveBeenCalledWith('链接无法解析')
  })

  it('tests the binding, refreshes the config and surfaces failures', async () => {
    rendered = renderCard()
    await settle()

    act(() => findButton(rendered!.container, '测试绑定')?.click())
    await settle()

    expect(mocks.testSafetyPageFeishuConfig).toHaveBeenCalledWith(
      'safety:risk-hazard:hazard-inspection:hazard-duty'
    )
    expect(mocks.message.success).toHaveBeenCalledWith('绑定正常')
    expect(mocks.getSafetyPageFeishuConfigs).toHaveBeenCalledTimes(2)

    // 测试失败分支
    mocks.testSafetyPageFeishuConfig.mockResolvedValueOnce({
      code: 200,
      data: { success: false, message: 'app_token 无效' },
    })
    act(() => findButton(rendered!.container, '测试绑定')?.click())
    await settle()
    expect(mocks.message.error).toHaveBeenCalledWith('app_token 无效')

    // 接口失败分支
    mocks.testSafetyPageFeishuConfig.mockResolvedValueOnce({
      code: 500,
      message: '后端不可用',
    })
    act(() => findButton(rendered!.container, '测试绑定')?.click())
    await settle()
    expect(mocks.message.error).toHaveBeenCalledWith('后端不可用')
  })

  it('preselects saved tab sub-tables and round-trips them on save', async () => {
    rendered = renderCard()
    await settle()

    // 已保存页签无需重新解析链接即可编辑：预勾选 + 可见
    expect(findSubTableOption(rendered.container, 'tblSubOld').checked).toBe(true)

    act(() => findButton(rendered!.container, '保存')?.click())
    await settle()

    expect(mocks.saveSafetyPageFeishuConfig).toHaveBeenCalledWith(
      'safety:risk-hazard:hazard-inspection:hazard-duty',
      expect.objectContaining({
        sub_tables: [
          { table_id: 'tblSubOld', tab_name: '2025年公司级检查', hidden_field_names: ['父记录'] },
        ],
      })
    )
    expect(mocks.message.success).toHaveBeenCalledWith('页面数据表绑定已保存')
  })

  it('lists sub-tables from a resolved link and saves the checked tabs', async () => {
    mocks.resolveSafetyPageFeishuUrl.mockResolvedValueOnce({
      code: 200,
      data: {
        app_token: 'bascnNew',
        table_id: 'tblNew',
        view_id: 'vewNew',
        is_wiki: false,
        tables: [
          { table_id: 'tblNew', table_name: '2026年公司级检查' },
          { table_id: 'tblSubA', table_name: '2025年集团检查' },
          { table_id: 'tblSubB', table_name: '观察项' },
        ],
      },
    })
    rendered = renderCard()
    await settle()

    setInput(
      rendered.container,
      '粘贴多维表格链接',
      'https://example.feishu.cn/base/bascnNew?table=tblNew&view=vewNew'
    )
    await settle()
    act(() => findButton(rendered!.container, '解析')?.click())
    await settle()

    // 换绑新 Base：旧页签不再可选，主表不在页签清单中，只列其余子表
    const optionValues = Array.from(
      rendered.container.querySelectorAll('input[type="checkbox"][data-option-value]')
    ).map((node) => (node as HTMLInputElement).dataset.optionValue)
    expect(optionValues).toEqual(['tblSubA', 'tblSubB'])

    toggleSubTable(rendered.container, 'tblSubA', true)
    await settle()
    act(() => findButton(rendered!.container, '保存')?.click())
    await settle()

    expect(mocks.saveSafetyPageFeishuConfig).toHaveBeenCalledWith(
      'safety:risk-hazard:hazard-inspection:hazard-duty',
      expect.objectContaining({
        table_id: 'tblNew',
        sub_tables: [
          { table_id: 'tblSubA', tab_name: '2025年集团检查', hidden_field_names: [] },
        ],
      })
    )
  })

  it('drops a tab sub-table when it becomes the primary table', async () => {
    rendered = renderCard()
    await settle()

    // 直接把保存过的页签子表升为主表（模拟用户改 Table ID 输入框）
    const tableIdInput = Array.from(rendered.container.querySelectorAll('input')).find(
      (node) => node.placeholder?.startsWith('数据表 table_id')
    ) as HTMLInputElement
    expect(tableIdInput.value).toBe('tblOld')
    act(() => {
      tableIdInput.value = 'tblSubOld'
      tableIdInput.dispatchEvent(new Event('change', { bubbles: true }))
    })
    await settle()

    act(() => findButton(rendered!.container, '保存')?.click())
    await settle()

    expect(mocks.saveSafetyPageFeishuConfig).toHaveBeenCalledWith(
      'safety:risk-hazard:hazard-inspection:hazard-duty',
      expect.objectContaining({
        table_id: 'tblSubOld',
        sub_tables: [],
      })
    )
  })
})