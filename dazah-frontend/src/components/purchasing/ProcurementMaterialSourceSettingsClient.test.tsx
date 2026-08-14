/* @vitest-environment happy-dom */

import { act, type ChangeEvent, type FormEvent, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const actions = vi.hoisted(() => ({
  saveProcurementMaterialSource: vi.fn(),
  testProcurementMaterialSource: vi.fn(),
}))

const messages = vi.hoisted(() => ({
  error: vi.fn(),
  success: vi.fn(),
  warning: vi.fn(),
}))

vi.mock('@/actions/purchasing', () => actions)

vi.mock('antd', () => {
  const Wrapper = ({ children }: { children?: ReactNode }) => <div>{children}</div>
  const Button = ({
    children,
    loading,
    onClick,
  }: {
    children?: ReactNode
    loading?: boolean
    onClick?: () => void
  }) => <button disabled={loading} onClick={onClick}>{children}</button>
  const Input = ({
    onChange,
    value,
    }: {
      onChange?: (event: ChangeEvent<HTMLInputElement>) => void
      value?: string
  }) => (
    <input
      value={value ?? ''}
      onChange={onChange}
      onInput={(event: FormEvent<HTMLInputElement>) => {
        onChange?.(event as unknown as ChangeEvent<HTMLInputElement>)
      }}
    />
  )
  const Text = ({ children }: { children?: ReactNode }) => <span>{children}</span>
  return {
    Alert: ({ message, description }: { message?: ReactNode; description?: ReactNode }) => (
      <div role="alert">{message}{description}</div>
    ),
    App: { useApp: () => ({ message: messages }) },
    Button,
    Card: Wrapper,
    Descriptions: Object.assign(Wrapper, { Item: Wrapper }),
    Input,
    Space: Wrapper,
    Tag: Wrapper,
    Typography: { Text },
  }
})

import { ProcurementMaterialSourceSettingsClient } from './ProcurementMaterialSourceSettingsClient'

const initialConfig = {
  id: 'config-1',
  source_url: 'https://feishu.cn/base/appToken123456?table=tbl123456',
  app_token: 'appToken123456',
  table_id: 'tbl123456',
  view_id: null,
  material_code_field: '物料编码',
  material_description_field: '物料说明',
  rule_model_field: '规格型号',
  last_test_status: 'success',
  last_test_error: null,
  last_tested_at: '2026-08-14T00:00:00Z',
  updated_at: '2026-08-14T00:00:00Z',
} as const

describe('ProcurementMaterialSourceSettingsClient', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    vi.clearAllMocks()
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
  })

  it('shows parsed configuration and tests the current link', async () => {
    actions.testProcurementMaterialSource.mockResolvedValue({
      code: 200,
      message: 'success',
      data: {
        source_url: initialConfig.source_url,
        app_token: initialConfig.app_token,
        table_id: initialConfig.table_id,
        view_id: null,
        material_code_field: '物料编码',
        material_description_field: '物料说明',
        rule_model_field: '规则型号',
        available_fields: ['物料编码', '物料说明', '规则型号'],
        status: 'success',
        error_message: null,
        tested_at: '2026-08-14T00:00:00Z',
      },
    })

    act(() => {
      root.render(
        <ProcurementMaterialSourceSettingsClient initialConfig={initialConfig} />,
      )
    })
    expect(container.textContent).toContain('规格型号字段')
    const input = container.querySelector('input') as HTMLInputElement
    const testButton = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent === '测试连接',
    )
    await act(async () => {
      input.value = initialConfig.source_url
      input.dispatchEvent(new Event('input', { bubbles: true }))
      testButton?.click()
      await Promise.resolve()
    })

    expect(actions.testProcurementMaterialSource).toHaveBeenCalledWith({
      source_url: initialConfig.source_url,
    })
    expect(container.textContent).toContain('规则型号')
  })

  it('keeps the entered link after a save failure', async () => {
    actions.saveProcurementMaterialSource.mockResolvedValue({
      code: 502,
      message: '飞书多维表格访问失败',
      data: null,
    })

    act(() => {
      root.render(<ProcurementMaterialSourceSettingsClient initialConfig={null} />)
    })
    const input = container.querySelector('input') as HTMLInputElement
    const sourceUrl = 'https://feishu.cn/base/newAppToken?table=tbl-new'
    act(() => {
      input.value = sourceUrl
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    const saveButton = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent === '保存配置',
    )
    await act(async () => {
      saveButton?.click()
      await Promise.resolve()
    })

    expect(actions.saveProcurementMaterialSource).toHaveBeenCalledWith({ source_url: sourceUrl })
    expect(input.value).toBe(sourceUrl)
  })

  it('requires a link before testing or saving', async () => {
    act(() => {
      root.render(<ProcurementMaterialSourceSettingsClient initialConfig={null} />)
    })

    const [testButton, saveButton] = Array.from(container.querySelectorAll('button'))
    await act(async () => {
      testButton.click()
      saveButton.click()
      await Promise.resolve()
    })

    expect(messages.warning).toHaveBeenCalledTimes(2)
    expect(actions.testProcurementMaterialSource).not.toHaveBeenCalled()
    expect(actions.saveProcurementMaterialSource).not.toHaveBeenCalled()
  })

  it('reports test failures returned by the backend and thrown by the action', async () => {
    actions.testProcurementMaterialSource
      .mockResolvedValueOnce({ code: 502, message: '飞书访问失败', data: null })
      .mockRejectedValueOnce(new Error('network'))

    act(() => {
      root.render(<ProcurementMaterialSourceSettingsClient initialConfig={initialConfig} />)
    })
    const testButton = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent === '测试连接',
    )
    await act(async () => {
      testButton?.click()
      await Promise.resolve()
    })
    expect(messages.error).toHaveBeenCalledWith('飞书访问失败')

    await act(async () => {
      testButton?.click()
      await Promise.resolve()
    })
    expect(messages.error).toHaveBeenCalledWith('物料数据源测试失败，请稍后重试')
  })

  it('saves a valid source and reports an unexpected save failure', async () => {
    const savedConfig = { ...initialConfig, id: 'saved-config' }
    actions.saveProcurementMaterialSource
      .mockResolvedValueOnce({ code: 200, message: 'success', data: savedConfig })
      .mockRejectedValueOnce(new Error('network'))

    act(() => {
      root.render(<ProcurementMaterialSourceSettingsClient initialConfig={initialConfig} />)
    })
    const saveButton = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent === '保存配置',
    )
    await act(async () => {
      saveButton?.click()
      await Promise.resolve()
    })
    expect(messages.success).toHaveBeenCalledWith('采购物料数据源配置已保存')

    await act(async () => {
      saveButton?.click()
      await Promise.resolve()
    })
    expect(messages.error).toHaveBeenCalledWith('物料数据源保存失败，请稍后重试')
  })
})
