/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  fetchMaterialCatalog: vi.fn(),
  fetchMaterialSourceConfig: vi.fn(),
}))

const messages = vi.hoisted(() => ({
  error: vi.fn(),
  success: vi.fn(),
}))

vi.mock('@/lib/api/purchasing', () => api)

vi.mock('antd', () => {
  const Wrapper = ({ children }: { children?: React.ReactNode }) => <div>{children}</div>
  const Button = ({
    children,
    onClick,
  }: {
    children?: React.ReactNode
    onClick?: () => void
  }) => <button onClick={onClick}>{children}</button>
  const Input = ({
    value,
    onChange,
    onPressEnter,
    placeholder,
  }: {
    value?: string
    onChange?: (event: React.ChangeEvent<HTMLInputElement>) => void
    onPressEnter?: () => void
    placeholder?: string
  }) => (
    <input
      placeholder={placeholder}
      value={value ?? ''}
      onChange={onChange}
      onKeyDown={(event) => {
        if (event.key === 'Enter') onPressEnter?.()
      }}
      onInput={(event) => onChange?.(event as unknown as React.ChangeEvent<HTMLInputElement>)}
    />
  )
  const Search = ({
    value,
    onChange,
    onSearch,
    placeholder,
  }: {
    value?: string
    onChange?: (event: React.ChangeEvent<HTMLInputElement>) => void
    onSearch?: () => void
    placeholder?: string
  }) => (
    <div>
      <Input value={value} onChange={onChange} placeholder={placeholder} />
      <button onClick={onSearch}>搜索</button>
    </div>
  )
  Object.assign(Input, { Search })

  return {
    Alert: ({ message, description }: { message?: React.ReactNode; description?: React.ReactNode }) => (
      <div role="alert">{message}{description}</div>
    ),
    App: { useApp: () => ({ message: messages }) },
    Button,
    Card: Wrapper,
    Input,
    Progress: ({ percent }: { percent?: number }) => (
      <div role="progressbar">{percent}</div>
    ),
    Space: Wrapper,
    Statistic: ({ title, value }: { title?: React.ReactNode; value?: React.ReactNode }) => (
      <div>{title}{value}</div>
    ),
    Table: ({ dataSource }: { dataSource?: Array<{ id: string; material_code: string }> }) => (
      <div>{dataSource?.map((record) => <div key={record.id}>{record.material_code}</div>)}</div>
    ),
    Tag: ({ children }: { children?: React.ReactNode }) => <span>{children}</span>,
  }
})

import { MaterialLibraryClient } from './MaterialLibraryClient'

const initialMeta = {
  page: 1,
  page_size: 20,
  total: 1,
  sync_status: 'success',
  sync_error: null,
  sync_phase: 'completed',
  sync_persisted_count: 1,
  last_synced_at: '2026-08-14T00:00:00Z',
  last_sync_record_count: 1,
} as const

const initialRecord = {
  id: 'record-1',
  feishu_record_id: 'rec-1',
  material_code: 'MAT-001',
  material_description: '第一条物料',
  rule_model: 'A 型',
  material_unit: '件',
  material_template: '模板A',
  material_category: '五金',
  material_subcategory: '螺丝',
  material_cost_category: '成本A',
  feishu_created_time: null,
  feishu_last_modified_time: null,
  last_synced_at: '2026-08-14T00:00:00Z',
} as const

describe('MaterialLibraryClient', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT =
      true
    vi.clearAllMocks()
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
  })

  it('shows synced records and sends all search filters to the API', async () => {
    api.fetchMaterialCatalog.mockResolvedValue({
      code: 200,
      message: 'success',
      data: [initialRecord],
      meta: initialMeta,
    })

    act(() => {
      root.render(
        <MaterialLibraryClient initialRecords={[initialRecord]} initialMeta={initialMeta} />,
      )
    })
    expect(container.textContent).toContain('MAT-001')

    const searchInput = container.querySelector(
      'input[placeholder="搜索编码、说明或规格型号"]',
    ) as HTMLInputElement
    const codeInput = container.querySelector('input[placeholder="物料编码"]') as HTMLInputElement
    act(() => {
      searchInput.value = 'MAT'
      searchInput.dispatchEvent(new Event('input', { bubbles: true }))
      codeInput.value = 'MAT-001'
      codeInput.dispatchEvent(new Event('input', { bubbles: true }))
    })
    const queryButton = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent === '查询',
    )
    await act(async () => {
      queryButton?.click()
      await Promise.resolve()
    })

    expect(api.fetchMaterialCatalog).toHaveBeenCalledWith({
      keyword: 'MAT',
      material_code: 'MAT-001',
      material_description: undefined,
      rule_model: undefined,
      page: 1,
      page_size: 20,
    })
  })

  it('shows live sync progress while a background sync is running', () => {
    act(() => {
      root.render(
        <MaterialLibraryClient
          initialRecords={[]}
          initialMeta={{
            ...initialMeta,
            total: 0,
            sync_status: 'syncing',
            sync_total_records: 1000,
            sync_fetched_count: 500,
          }}
        />,
      )
    })

    expect(container.textContent).toContain('已同步 500 / 1000 条')
    expect(container.querySelector('[role="progressbar"]')?.textContent).toBe('50')
  })

  it('shows a waiting hint before the first page arrives', () => {
    act(() => {
      root.render(
        <MaterialLibraryClient
          initialRecords={[]}
          initialMeta={{
            ...initialMeta,
            total: 0,
            sync_status: 'syncing',
            sync_total_records: null,
            sync_fetched_count: 0,
          }}
        />,
      )
    })

    expect(container.textContent).toContain('正在请求飞书首个页面')
  })

  it('polls while syncing and reloads records once the sync completes', async () => {
    vi.useFakeTimers()
    try {
      api.fetchMaterialSourceConfig.mockResolvedValue({
        code: 200,
        message: 'success',
        data: {
          sync_status: 'success',
          sync_error: null,
          last_synced_at: '2026-08-14T01:00:00Z',
          last_sync_record_count: 3,
          sync_total_records: null,
          sync_fetched_count: null,
        },
      })
      api.fetchMaterialCatalog.mockResolvedValue({
        code: 200,
        message: 'success',
        data: [initialRecord],
        meta: { ...initialMeta, sync_status: 'success', last_sync_record_count: 3 },
      })

      act(() => {
        root.render(
          <MaterialLibraryClient
            initialRecords={[]}
            initialMeta={{ ...initialMeta, total: 0, sync_status: 'syncing' }}
          />,
        )
      })
      expect(container.textContent).toContain('同步中')

      await act(async () => {
        await vi.advanceTimersByTimeAsync(3000)
      })

      expect(api.fetchMaterialSourceConfig).toHaveBeenCalledOnce()
      expect(messages.success).toHaveBeenCalledWith(
        '采购物料数据同步完成，本地记录 3 条',
      )
      expect(api.fetchMaterialCatalog).toHaveBeenCalledTimes(1)
      expect(container.textContent).toContain('MAT-001')
      expect(container.textContent).toContain('同步成功')
    } finally {
      vi.useRealTimers()
    }
  })

  it('reports a recoverable load failure without hiding the existing records', async () => {
    api.fetchMaterialCatalog.mockRejectedValue(new Error('network'))

    act(() => {
      root.render(
        <MaterialLibraryClient initialRecords={[initialRecord]} initialMeta={initialMeta} />,
      )
    })
    const refreshButton = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent === '刷新',
    )
    await act(async () => {
      refreshButton?.click()
      await Promise.resolve()
    })

    expect(messages.error).toHaveBeenCalledWith('物料编码库加载失败，请稍后重试')
    expect(container.textContent).toContain('MAT-001')
  })
})
