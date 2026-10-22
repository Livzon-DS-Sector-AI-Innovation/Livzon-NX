/* @vitest-environment happy-dom */

import {
  act,
  createContext,
  type ReactNode,
  useContext,
  useSyncExternalStore,
} from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  createFeishuApp: vi.fn(),
  deleteFeishuApp: vi.fn(),
  fetchFeishuApps: vi.fn(),
  updateFeishuApp: vi.fn(),
}))

const messages = vi.hoisted(() => ({
  error: vi.fn(),
  info: vi.fn(),
  success: vi.fn(),
  warning: vi.fn(),
}))

vi.mock('@/lib/api/inspection-feishu', () => api)

vi.mock('antd', async () => {
  const { useState: reactUseState } = await import('react')
  type FieldBinding = {
    name?: string
    store: Record<string, unknown>
    subscribe: (listener: () => void) => () => void
    getVersion: () => number
    setValue: (name: string, value: unknown) => void
  }
  const FieldContext = createContext<FieldBinding>({
    store: {},
    subscribe: () => () => undefined,
    getVersion: () => 0,
    setValue: () => undefined,
  })

  const makeMockForm = () => {
    const store: Record<string, unknown> = {}
    const listeners = new Set<() => void>()
    let version = 0
    const emit = () => {
      version += 1
      listeners.forEach((listener) => listener())
    }
    const binding = {
      store,
      subscribe: (listener: () => void) => {
        listeners.add(listener)
        return () => {
          listeners.delete(listener)
        }
      },
      getVersion: () => version,
      setValue: (name: string, value: unknown) => {
        store[name] = value
        emit()
      },
    }
    return {
      __binding: binding,
      setFieldsValue: (values: Record<string, unknown>) => {
        Object.assign(store, values)
        emit()
      },
      resetFields: () => {
        Object.keys(store).forEach((key) => delete store[key])
        emit()
      },
      validateFields: async () => ({ ...store }),
    }
  }

  const Button = ({ children, onClick, ['aria-label']: ariaLabel }: {
    children?: ReactNode; onClick?: () => void; ['aria-label']?: string
  }) => (
    <button aria-label={ariaLabel} onClick={onClick}>{children}</button>
  )
  const MockInput = ({ placeholder }: { placeholder?: string }) => {
    const binding = useContext(FieldContext)
    useSyncExternalStore(binding.subscribe, binding.getVersion, binding.getVersion)
    const boundValue = binding.name && binding.name in binding.store
      ? String(binding.store[binding.name] ?? '')
      : ''
    return (
      <input
        aria-label={placeholder}
        placeholder={placeholder}
        value={boundValue}
        onChange={(event) => {
          if (binding.name) binding.setValue(binding.name, event.target.value)
        }}
      />
    )
  }
  return {
    App: { useApp: () => ({ message: messages }) },
    Button,
    Card: ({ children, extra, title }: { children?: ReactNode; extra?: ReactNode; title?: ReactNode }) => (
      <section>
        <header>{title}{extra}</header>
        {children}
      </section>
    ),
    Form: Object.assign(
      ({ children, form }: { children?: ReactNode; form?: { __binding?: FieldBinding } }) => (
        <FieldContext.Provider value={form?.__binding ?? { store: {}, subscribe: () => () => undefined, getVersion: () => 0, setValue: () => undefined }}>
          <form>{children}</form>
        </FieldContext.Provider>
      ),
      {
        Item: ({ children, name }: { children?: ReactNode; name?: string }) => (
          <FieldContextScoper name={name}>{children}</FieldContextScoper>
        ),
        useForm: () => reactUseState(() => [makeMockForm()])[0],
      },
    ),
    Input: Object.assign(MockInput, { Password: MockInput }),
    Modal: ({
      children, open, title, onOk,
    }: {
      children?: ReactNode; open?: boolean; title?: ReactNode; onOk?: () => void
    }) => (open ? (
      <div role="modal">
        <div>{title}</div>
        {children}
        <button role="modal-ok" onClick={onOk}>确定</button>
      </div>
    ) : null),
    Popconfirm: ({ children, onConfirm }: { children?: ReactNode; onConfirm?: () => void }) => (
      <span>
        {children}
        <button role="popconfirm-ok" onClick={onConfirm}>确认删除</button>
      </span>
    ),
    Space: ({ children }: { children?: ReactNode }) => <span>{children}</span>,
    Table: ({ dataSource, columns }: {
      dataSource?: Array<Record<string, unknown>>
      columns?: Array<{ dataIndex?: string; render?: (v: unknown, row: Record<string, unknown>) => ReactNode; title?: ReactNode }>
    }) => (
      <table>
        <thead><tr>{(columns ?? []).map((col, i) => <th key={i}>{col.title}</th>)}</tr></thead>
        <tbody>
          {(dataSource ?? []).map((row, i) => (
            <tr key={String(row.id ?? i)}>
              {(columns ?? []).map((col, j) => (
                <td key={j}>
                  {col.render
                    ? col.render(col.dataIndex ? row[col.dataIndex] : undefined, row)
                    : ((col.dataIndex ? row[col.dataIndex] : null) as ReactNode)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    ),
    Tag: ({ children }: { children?: ReactNode }) => <span>{children}</span>,
    Typography: {
      Text: ({ children }: { children?: ReactNode }) => <span>{children}</span>,
      Paragraph: ({ children }: { children?: ReactNode }) => <p>{children}</p>,
    },
  }

  function FieldContextScoper({ children, name }: { children?: ReactNode; name?: string }) {
    const binding = useContext(FieldContext)
    const scoped = name ? { ...binding, name } : binding
    return <FieldContext.Provider value={scoped}>{children}</FieldContext.Provider>
  }
})

vi.mock('@ant-design/icons', () => {
  const icon = () => <i />
  return {
    ApiOutlined: icon,
    CopyOutlined: icon,
    DeleteOutlined: icon,
    EditOutlined: icon,
    PlusOutlined: icon,
  }
})

import { FeishuAppLibraryCard } from './FeishuAppLibraryCard'
import type { FeishuAppItem } from '@/types/inspection-feishu'

const app = (overrides: Partial<FeishuAppItem> = {}): FeishuAppItem => ({
  id: 'app-1',
  name: '巡检同步应用',
  app_id: 'cli_a1',
  app_secret_configured: true,
  referenced_workshops: ['101-1'],
  created_at: '2026-10-20T08:00:00Z',
  updated_at: '2026-10-21T08:00:00Z',
  ...overrides,
})

describe('FeishuAppLibraryCard 自建应用库', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    vi.clearAllMocks()
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    api.fetchFeishuApps.mockResolvedValue([
      app(),
      app({
        id: 'app-2', name: '备用应用', app_id: 'cli_b2',
        app_secret_configured: false, referenced_workshops: [],
      }),
    ])
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
  })

  const renderCard = async (onChanged?: () => void) => {
    await act(async () => {
      root.render(<FeishuAppLibraryCard onChanged={onChanged} />)
      await Promise.resolve()
      await Promise.resolve()
    })
  }

  const clickByText = async (text: string) => {
    await act(async () => {
      const btn = [...container.querySelectorAll('button')].find((b) => b.textContent?.includes(text))
      btn?.click()
      await Promise.resolve()
    })
  }

  const saveModal = async () => {
    await act(async () => {
      ;(container.querySelector('[role="modal-ok"]') as HTMLElement).click()
      await Promise.resolve()
      await Promise.resolve()
      await Promise.resolve()
      await Promise.resolve()
    })
  }

  it('loads and renders app rows with secret/reference status', async () => {
    await renderCard()
    const text = container.textContent || ''
    expect(text).toContain('巡检同步应用')
    expect(text).toContain('cli_a1')
    expect(text).toContain('已配置')
    expect(text).toContain('未配置')
    expect(text).toContain('101-1')
    expect(text).toContain('未引用')
    expect(api.fetchFeishuApps).toHaveBeenCalledOnce()
  })

  it('shows a readable error when loading fails', async () => {
    api.fetchFeishuApps.mockRejectedValue(new Error('未登录'))
    await renderCard()
    expect(container.textContent).toContain('加载自建应用失败：未登录')
  })

  it('creates an app through the modal and notifies onChanged', async () => {
    api.createFeishuApp.mockResolvedValue(app())
    const onChanged = vi.fn()
    await renderCard(onChanged)
    await clickByText('新建应用')
    // 表单经 mock 绑定输入值后保存
    const inputs = [...container.querySelectorAll<HTMLInputElement>('[role="modal"] input')]
    expect(inputs.length).toBeGreaterThanOrEqual(3)
    await act(async () => {
      inputs[0].dispatchEvent(new Event('input', { bubbles: true }))
      await Promise.resolve()
    })
    // 用原生 setter 写值（绕过 React 受控）
    const setNative = (el: HTMLInputElement, value: string) => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set
      setter?.call(el, value)
      el.dispatchEvent(new Event('input', { bubbles: true }))
    }
    await act(async () => {
      setNative(inputs[0], '  新巡检应用  ')
      setNative(inputs[1], 'cli_new')
      setNative(inputs[2], 'secret-value')
      await Promise.resolve()
    })
    await saveModal()
    expect(api.createFeishuApp).toHaveBeenCalledWith({
      name: '新巡检应用',
      app_id: 'cli_new',
      app_secret: 'secret-value',
    })
    expect(messages.success).toHaveBeenCalledWith('自建应用已创建')
    expect(onChanged).toHaveBeenCalledOnce()
  })

  it('updates an app keeping the stored secret when left blank', async () => {
    api.updateFeishuApp.mockResolvedValue(app())
    await renderCard()
    await clickByText('编辑')
    expect(container.textContent).toContain('编辑自建应用 · 巡检同步应用')
    await saveModal()
    expect(api.updateFeishuApp).toHaveBeenCalledWith('app-1', {
      name: '巡检同步应用',
      app_id: 'cli_a1',
      app_secret: null,
    })
    expect(messages.success).toHaveBeenCalledWith('自建应用已更新')
  })

  it('surfaces save failure without crashing', async () => {
    api.updateFeishuApp.mockRejectedValue(new Error('App ID 已存在'))
    await renderCard()
    await clickByText('编辑')
    await saveModal()
    expect(messages.error).toHaveBeenCalledWith('App ID 已存在')
  })

  it('deletes an app after confirmation and reloads', async () => {
    api.deleteFeishuApp.mockResolvedValue(null)
    const onChanged = vi.fn()
    await renderCard(onChanged)
    await act(async () => {
      ;(container.querySelector('[role="popconfirm-ok"]') as HTMLElement).click()
      await Promise.resolve()
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(api.deleteFeishuApp).toHaveBeenCalledWith('app-1')
    expect(messages.success).toHaveBeenCalled()
    expect(onChanged).toHaveBeenCalledOnce()
  })

  it('surfaces delete rejection from the backend', async () => {
    api.deleteFeishuApp.mockRejectedValue(new Error('应用仍被巡检配置引用，无法删除'))
    await renderCard()
    await act(async () => {
      ;(container.querySelector('[role="popconfirm-ok"]') as HTMLElement).click()
      await Promise.resolve()
      await Promise.resolve()
      await Promise.resolve()
    })
    expect(messages.error).toHaveBeenCalledWith('应用仍被巡检配置引用，无法删除')
  })

  it('copies App ID to the clipboard and reports failure when blocked', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    await renderCard()
    await act(async () => {
      const copyBtn = container.querySelector('[aria-label="复制应用 App ID cli_a1"]') as HTMLElement
      copyBtn.click()
      await Promise.resolve()
    })
    expect(writeText).toHaveBeenCalledWith('cli_a1')
    expect(messages.success).toHaveBeenCalledWith('已复制App ID')

    writeText.mockRejectedValue(new Error('denied'))
    await act(async () => {
      const copyBtn = container.querySelector('[aria-label="复制应用 App ID cli_a1"]') as HTMLElement
      copyBtn.click()
      await Promise.resolve()
    })
    expect(messages.error).toHaveBeenCalledWith('复制失败，请手动选择复制')
  })
})
