/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { FeishuPersonSelect, type FeishuPersonValue } from './FeishuPersonSelect'

const mocks = vi.hoisted(() => ({
  fetchValidationPersonOptions: vi.fn(),
}))

vi.mock('@/lib/api/client/quality', () => ({
  fetchValidationPersonOptions: mocks.fetchValidationPersonOptions,
}))

const DIRECTORY = [
  { open_id: 'ou_zhang', name: '张三', department: '质量部', job_title: 'QA' },
  { open_id: 'ou_li', name: '李四', department: '生产部', job_title: null },
  { open_id: 'ou_wang', name: 'Wang', department: null, job_title: null },
]

let container: HTMLElement
let root: Root
let queryClient: QueryClient

function renderSelect(props: Partial<Parameters<typeof FeishuPersonSelect>[0]> = {}) {
  act(() => {
    root.render(
      <QueryClientProvider client={queryClient}>
        <FeishuPersonSelect onChange={vi.fn()} {...props} />
      </QueryClientProvider>,
    )
  })
}

async function openDropdown() {
  const select = container.querySelector('.ant-select') as HTMLElement
  await act(async () => {
    select.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
    await new Promise((resolve) => setTimeout(resolve, 80))
  })
}

async function typeInSearch(keyword: string) {
  const input = (container.querySelector('.ant-select') as HTMLElement | null)?.querySelector(
    'input',
  ) as HTMLInputElement | null
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      'value',
    )?.set
    setter?.call(input, keyword)
    input?.dispatchEvent(new Event('input', { bubbles: true }))
    await new Promise((resolve) => setTimeout(resolve, 60))
  })
}

function optionLabels(): string[] {
  return Array.from(document.body.querySelectorAll('.ant-select-item-option')).map(
    (node) => node.textContent || '',
  )
}

async function clickOption(label: string) {
  const option = Array.from(
    document.body.querySelectorAll('.ant-select-item-option'),
  ).find((node) => (node.textContent || '').includes(label)) as HTMLElement | undefined
  await act(async () => {
    option?.click()
    await new Promise((resolve) => setTimeout(resolve, 60))
  })
}

describe('FeishuPersonSelect', () => {
  beforeEach(() => {
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    mocks.fetchValidationPersonOptions.mockResolvedValue(DIRECTORY)
  })

  afterEach(async () => {
    await act(async () => {
      queryClient.clear()
      root.unmount()
    })
    container.remove()
    vi.clearAllMocks()
  })

  it('loads the HR feishu directory and selects a person by open_id', async () => {
    const onChange = vi.fn()
    renderSelect({ onChange })
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50))
    })
    expect(mocks.fetchValidationPersonOptions).toHaveBeenCalledWith(undefined, 500)

    await openDropdown()
    // 选项展示带部门后缀，便于区分重名
    expect(optionLabels()).toEqual(expect.arrayContaining(['张三（质量部）', '李四（生产部）']))

    await clickOption('张三')
    expect(onChange).toHaveBeenCalledWith({
      id: 'ou_zhang',
      name: '张三',
      resolved: false,
    })
  })

  it('filters options by full pinyin and initials', async () => {
    renderSelect()
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50))
    })

    await openDropdown()
    await typeInSearch('zhangsan')
    expect(optionLabels()).toContain('张三（质量部）')
    expect(optionLabels()).not.toContain('李四')

    await typeInSearch('ls')
    expect(optionLabels()).toContain('李四（生产部）')
    expect(optionLabels()).not.toContain('张三')
  })

  it('filters locally without re-querying the directory api on search', async () => {
    renderSelect()
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50))
    })
    mocks.fetchValidationPersonOptions.mockClear()

    await openDropdown()
    await typeInSearch('李四')
    // 搜索为客户端过滤（拼音/首字母），不再触发目录 API 请求
    expect(mocks.fetchValidationPersonOptions).not.toHaveBeenCalled()
    expect(optionLabels()).toContain('李四（生产部）')
  })

  it('merges record prefill entries into the options', async () => {
    const prefill: FeishuPersonValue[] = [{ id: 'bid_legacy', name: '赵六' }]
    renderSelect({ extraOptions: prefill, value: prefill })
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50))
    })

    // 回显值直接显示在选区中
    expect(container.textContent).toContain('赵六')

    await openDropdown()
    expect(optionLabels()).toContain('赵六')
    expect(optionLabels()).toContain('张三（质量部）')
  })
})
