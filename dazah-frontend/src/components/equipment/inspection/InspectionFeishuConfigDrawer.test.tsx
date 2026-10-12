/* @vitest-environment happy-dom */

import {
  act,
  createContext,
  type ChangeEvent,
  type CSSProperties,
  type FocusEvent,
  type ReactNode,
  useContext,
  useState,
  useSyncExternalStore,
} from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  fetchInspectionFeishuConfig: vi.fn(),
  updateInspectionFeishuConfig: vi.fn(),
  testInspectionFeishuConfig: vi.fn(),
}))

const messages = vi.hoisted(() => ({
  error: vi.fn(),
  info: vi.fn(),
  success: vi.fn(),
  warning: vi.fn(),
}))

vi.mock('@/lib/api/inspection-feishu', () => api)

// 注意：@tanstack/react-query 不 mock——抽屉自带 Provider，用真实库渲染
// 才能回归「页面无模块级 QueryClient 时抽屉抛错」这类问题。

vi.mock('antd', async () => {
  // 工厂内定义：vi.mock 工厂在测试模块体初始化前执行，不能引用模块级 const
  type FieldApi = {
    store: Record<string, unknown>
    subscribe: (listener: () => void) => () => void
    getVersion: () => number
    setValue: (name: string, value: unknown) => void
  }
  type FieldBinding = FieldApi & { name?: string }
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
    const api: FieldApi = {
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
      __fieldApi: api,
      setFieldsValue: (values: Record<string, unknown>) => {
        Object.assign(store, values)
        emit()
      },
      setFieldValue: (name: string, value: unknown) => {
        store[name] = value
        emit()
      },
      getFieldValue: (name: string) => store[name],
      validateFields: async () => ({ ...store }),
    }
  }

  const Button = ({
    children, loading, onClick, type,
  }: {
    children?: ReactNode
    loading?: boolean
    onClick?: () => void
    type?: string
  }) => (
    <button disabled={loading} data-type={type} onClick={onClick}>
      {children}
    </button>
  )
  const MockInput = ({
    onChange,
    onBlur,
    placeholder,
  }: {
    onChange?: (event: ChangeEvent<HTMLInputElement>) => void
    onBlur?: (event: FocusEvent<HTMLInputElement>) => void
    placeholder?: string
  }) => {
    const binding = useContext(FieldContext)
    useSyncExternalStore(binding.subscribe, binding.getVersion, binding.getVersion)
    const boundValue = binding.name && binding.name in binding.store
      ? String(binding.store[binding.name] ?? '')
      : ''
    return (
      <input
        placeholder={placeholder}
        value={boundValue}
        onChange={(event) => {
          if (binding.name) binding.setValue(binding.name, event.target.value)
          onChange?.(event)
        }}
        onBlur={(event) => onBlur?.(event)}
      />
    )
  }
  const Password = (props: Parameters<typeof MockInput>[0]) => (
    <MockInput {...props} />
  )
  return {
    App: { useApp: () => ({ message: messages }) },
    Button,
    Drawer: ({
      children, footer, open, title,
    }: {
      children?: ReactNode
      footer?: ReactNode
      open?: boolean
      title?: ReactNode
    }) => (open ? (
      <div>
        <div>{title}</div>
        {children}
        {footer}
      </div>
    ) : null),
    Form: Object.assign(
      ({ children, form }: { children?: ReactNode; form?: unknown }) => {
        const api = (form as { __fieldApi?: FieldApi })?.__fieldApi
        const fallback: FieldApi = {
          store: {},
          subscribe: () => () => undefined,
          getVersion: () => 0,
          setValue: () => undefined,
        }
        return (
          <FieldContext.Provider value={api ?? fallback}>
            {children}
          </FieldContext.Provider>
        )
      },
      {
        Item: ({
          children, extra, name,
        }: { children?: ReactNode; extra?: ReactNode; name?: string }) => (
          <FieldContext.Consumer>
            {(parent) => (
              <FieldContext.Provider value={{ ...parent, name }}>
                <label>
                  {children}
                  {extra ? <small>{extra}</small> : null}
                </label>
              </FieldContext.Provider>
            )}
          </FieldContext.Consumer>
        ),
        useForm: () => {
          // 每次渲染新建实例会断开订阅，用 useState 保证组件生命周期内稳定
          const [form] = useState(() => makeMockForm())
          return [form]
        },
      },
    ),
    Input: Object.assign(MockInput, { Password }),
    Space: ({
      children, orientation,
    }: { children?: ReactNode; orientation?: string }) => (
      <div data-orientation={orientation} style={{ display: 'flex' } as CSSProperties}>
        {children}
      </div>
    ),
    Switch: () => {
      const binding = useContext(FieldContext)
      useSyncExternalStore(binding.subscribe, binding.getVersion, binding.getVersion)
      return (
        <input
          type="checkbox"
          checked={Boolean(binding.name && binding.store[binding.name])}
          onChange={(event) => {
            if (binding.name) {
              binding.setValue(binding.name, event.target.checked)
            }
          }}
        />
      )
    },
    Tag: ({ children, color }: { children?: ReactNode; color?: string }) => (
      <span data-tag-color={color}>{children}</span>
    ),
    Typography: {
      Paragraph: ({ children }: { children?: ReactNode }) => <p>{children}</p>,
    },
  }
})

import { InspectionFeishuConfigDrawer } from './InspectionFeishuConfigDrawer'

const detailFixture = {
  app_id: 'cli_fixture',
  app_secret_masked: 'cli_fixtur****',
  app_secret_configured: true,
  app_token: 'bascn_fixture',
  today_table_id: 'tbl_today',
  history_table_id: 'tbl_history',
  device_table_id: 'tbl_devices',
  is_enabled: true,
  source: 'database',
  enabled: true,
  last_test_status: 'success',
  last_test_error: null,
  last_tested_at: '2026-10-10T02:00:00Z',
} as const

function findButton(text: string): HTMLButtonElement {
  const buttons = Array.from(document.body.querySelectorAll('button'))
  const target = buttons.find((button) => button.textContent === text)
  if (!target) throw new Error(`button not found: ${text}`)
  return target
}

function findInputByPlaceholder(placeholder: string): HTMLInputElement {
  const inputs = Array.from(document.body.querySelectorAll('input'))
  const target = inputs.find((input) => input.placeholder === placeholder)
  if (!target) throw new Error(`input not found: ${placeholder}`)
  return target
}

/** React 会跟踪 value setter 去重 input 事件，需用原型原生 setter 赋值 */
function setInputValue(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(
    HTMLInputElement.prototype,
    'value',
  )?.set
  setter?.call(input, value)
  input.dispatchEvent(new Event('input', { bubbles: true }))
}

describe('InspectionFeishuConfigDrawer', () => {
  let container: HTMLDivElement
  let root: Root
  const onClose = vi.fn()
  const onSaved = vi.fn()

  beforeEach(() => {
    ;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT =
      true
    vi.clearAllMocks()
    api.fetchInspectionFeishuConfig.mockResolvedValue(detailFixture)
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
  })

  async function renderDrawer() {
    await act(async () => {
      root.render(
        <InspectionFeishuConfigDrawer open onClose={onClose} onSaved={onSaved} />,
      )
    })
    // 真实 react-query 的 fetch 完成与回填 effect 需要若干宏任务节拍
    for (let i = 0; i < 5; i += 1) {
      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 0))
      })
    }
  }

  it('renders summary and prefills fields from loaded config', async () => {
    await renderDrawer()

    expect(document.body.textContent).toContain('飞书同步配置')
    expect(document.body.textContent).toContain('数据库配置')
    expect(document.body.textContent).toContain('同步已启用')
    const appIdInput = findInputByPlaceholder('cli_xxxxxxxx')
    expect(appIdInput.value).toBe('cli_fixture')
    const tokenInput = findInputByPlaceholder('bascnxxxxxxxx 或多维表格链接')
    expect(tokenInput.value).toBe('bascn_fixture')
    // Secret 一律留空，由掩码提示表达已保存状态
    expect(document.body.textContent).toContain('留空保持不变')
  })

  it('saves config without resending the secret and notifies parent', async () => {
    api.updateInspectionFeishuConfig.mockResolvedValue(detailFixture)
    await renderDrawer()

    await act(async () => {
      findButton('保存配置').click()
    })

    expect(api.updateInspectionFeishuConfig).toHaveBeenCalledWith({
      app_id: 'cli_fixture',
      app_secret: null,
      app_token: 'bascn_fixture',
      today_table_id: 'tbl_today',
      history_table_id: 'tbl_history',
      device_table_id: 'tbl_devices',
      is_enabled: true,
    })
    expect(messages.success).toHaveBeenCalledWith('飞书配置已保存')
    expect(onSaved).toHaveBeenCalled()
  })

  it('keeps the drawer open and shows error when save fails', async () => {
    api.updateInspectionFeishuConfig.mockRejectedValue(
      new Error('启用同步需完整填写 App ID、App Secret 与多维表格 App Token'),
    )
    await renderDrawer()

    await act(async () => {
      findButton('保存配置').click()
    })

    expect(messages.error).toHaveBeenCalledWith(
      '启用同步需完整填写 App ID、App Secret 与多维表格 App Token',
    )
    expect(onSaved).not.toHaveBeenCalled()
    expect(document.body.textContent).toContain('飞书同步配置')
  })

  it('reports connection test result via message', async () => {
    api.testInspectionFeishuConfig.mockResolvedValue({
      success: true,
      table_count: 2,
      message: '连接成功，读取到 2 张子表',
    })
    await renderDrawer()

    await act(async () => {
      findButton('测试连接（已保存配置）').click()
    })

    expect(api.testInspectionFeishuConfig).toHaveBeenCalled()
    expect(messages.success).toHaveBeenCalledWith('连接成功，读取到 2 张子表')
  })

  it('extracts app token when a base url is pasted', async () => {
    await renderDrawer()

    const tokenInput = findInputByPlaceholder('bascnxxxxxxxx 或多维表格链接')
    await act(async () => {
      setInputValue(
        tokenInput,
        'https://x.feishu.cn/base/bascnPasted123?table=tblA&view=vewB',
      )
    })
    await act(async () => {
      tokenInput.dispatchEvent(new FocusEvent('focusout', { bubbles: true }))
    })

    expect(tokenInput.value).toBe('bascnPasted123')
    expect(messages.success).toHaveBeenCalledWith('已从链接提取 App Token')
  })

  it('keeps wiki links as-is with a hint', async () => {
    await renderDrawer()

    const tokenInput = findInputByPlaceholder('bascnxxxxxxxx 或多维表格链接')
    const wikiUrl = 'https://x.feishu.cn/wiki/WikiNodeToken1?table=tblA'
    await act(async () => {
      setInputValue(tokenInput, wikiUrl)
    })
    await act(async () => {
      tokenInput.dispatchEvent(new FocusEvent('focusout', { bubbles: true }))
    })

    expect(tokenInput.value).toBe(wikiUrl)
    expect(messages.info).toHaveBeenCalledWith(
      '已识别知识库链接，保存时将自动解析为多维表格 App Token',
    )
  })

  it('shows load error when config cannot be fetched', async () => {
    api.fetchInspectionFeishuConfig.mockRejectedValue(
      new Error('需要登录才能执行此操作'),
    )
    await renderDrawer()
    // Provider 配置 retry: 1，等待一次重试的指数退避（约 1s）后进入错误态
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 1300))
    })

    expect(document.body.textContent).toContain(
      '加载飞书配置失败：需要登录才能执行此操作',
    )
  })
})
