/* @vitest-environment happy-dom */

import { act, type ChangeEvent, type FormEvent, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const actions = vi.hoisted(() => ({
  saveProcurementMaterialSource: vi.fn(),
  syncProcurementMaterialSource: vi.fn(),
  testProcurementMaterialSource: vi.fn(),
}))

const materialSourceApi = vi.hoisted(() => ({
  fetchMaterialSourceConfig: vi.fn(),
}))

const messages = vi.hoisted(() => ({
  error: vi.fn(),
  info: vi.fn(),
  success: vi.fn(),
  warning: vi.fn(),
}))

vi.mock('@/actions/purchasing', () => actions)

vi.mock('@/lib/api/purchasing', () => materialSourceApi)

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
    Descriptions: Object.assign(Wrapper, {
      Item: ({
        children,
        label,
      }: {
        children?: ReactNode
        label?: ReactNode
      }) => <div>{label}{children}</div>,
    }),
    Input,
    Modal: {
      confirm: ({ onOk }: { onOk?: () => Promise<void> }) => {
        void onOk?.()
      },
    },
    Progress: ({ percent }: { percent?: number }) => (
      <div role="progressbar">{percent}</div>
    ),
    Space: Wrapper,
    Tag: Wrapper,
    Typography: { Text },
  }
})

import {
  MATERIAL_SYNC_HEARTBEAT_TIMEOUT_MS,
  MATERIAL_SYNC_POLL_INTERVAL_MS,
  ProcurementMaterialSourceSettingsClient,
} from './ProcurementMaterialSourceSettingsClient'

const initialConfig = {
  id: 'config-1',
  source_url: 'https://feishu.cn/base/appToken123456?table=tbl123456',
  app_token: 'appToken123456',
  table_id: 'tbl123456',
  view_id: null,
  material_code_field: '物料编码',
  material_description_field: '物料说明',
  rule_model_field: '规格型号',
  material_unit_field: '主要单位',
  material_template_field: '物料模板',
  material_category_field: '物料大类',
  material_subcategory_field: '物料小类',
  material_cost_category_field: '物料成本大类',
  last_test_status: 'success',
  last_test_error: null,
  last_tested_at: '2026-08-14T00:00:00Z',
  sync_status: 'success',
  sync_error: null,
  sync_phase: 'completed',
  sync_persisted_count: 0,
  last_synced_at: '2026-08-14T00:00:00Z',
  last_sync_record_count: 12,
  updated_at: '2026-08-14T00:00:00Z',
} as const

describe('ProcurementMaterialSourceSettingsClient', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    // 轮询测试使用 fake timers 驱动定时器，需要显式启用 act 环境跟踪
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
    expect(container.textContent).toContain('主要单位字段')
    expect(container.textContent).toContain('物料模板字段')
    expect(container.textContent).toContain('物料大类字段')
    expect(container.textContent).toContain('物料小类字段')
    expect(container.textContent).toContain('物料成本大类字段')
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

  it('reports already-saved link without calling save again', async () => {
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

    expect(actions.saveProcurementMaterialSource).not.toHaveBeenCalled()
    expect(messages.info).toHaveBeenCalledWith('该链接已保存，无需重复保存')
  })

  it('saves a valid source and reports an unexpected save failure on a changed link', async () => {
    const firstUrl = 'https://feishu.cn/base/newAppToken?table=tbl-new'
    const savedConfig = { ...initialConfig, id: 'saved-config', source_url: firstUrl }
    actions.saveProcurementMaterialSource
      .mockResolvedValueOnce({ code: 200, message: 'success', data: savedConfig })
      .mockRejectedValueOnce(new Error('network'))

    act(() => {
      root.render(<ProcurementMaterialSourceSettingsClient initialConfig={initialConfig} />)
    })
    const input = container.querySelector('input') as HTMLInputElement
    const saveButton = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent === '保存配置',
    )
    act(() => {
      input.value = firstUrl
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await act(async () => {
      saveButton?.click()
      await Promise.resolve()
    })
    expect(messages.success).toHaveBeenCalledWith('采购物料数据源配置已保存')

    // 链接未变再次点击只会提示已保存，不再请求接口
    await act(async () => {
      saveButton?.click()
      await Promise.resolve()
    })
    expect(actions.saveProcurementMaterialSource).toHaveBeenCalledTimes(1)
    expect(messages.info).toHaveBeenCalledWith('该链接已保存，无需重复保存')

    // 修改链接后再保存，接口异常时仍然报错
    const secondUrl = 'https://feishu.cn/base/otherAppToken?table=tbl-other'
    act(() => {
      input.value = secondUrl
      input.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await act(async () => {
      saveButton?.click()
      await Promise.resolve()
    })
    expect(actions.saveProcurementMaterialSource).toHaveBeenLastCalledWith({
      source_url: secondUrl,
    })
    expect(messages.error).toHaveBeenCalledWith('物料数据源保存失败，请稍后重试')
  })

  it('shows live sync progress while the background sync is running', () => {
    act(() => {
      root.render(
        <ProcurementMaterialSourceSettingsClient
          initialConfig={{
            ...initialConfig,
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

  it('shows the first-page request while fetching starts', () => {
    act(() => {
      root.render(
        <ProcurementMaterialSourceSettingsClient
          initialConfig={{
            ...initialConfig,
            sync_status: 'syncing',
            sync_phase: 'fetching',
            sync_total_records: null,
            sync_fetched_count: 0,
          }}
        />,
      )
    })

    expect(container.textContent).toContain('正在请求飞书首个页面')
  })

  it('shows a retry hint when the sync heartbeat is stale', () => {
    const staleHeartbeat = new Date(
      Date.now() - (MATERIAL_SYNC_HEARTBEAT_TIMEOUT_MS + 1000),
    ).toISOString()
    act(() => {
      root.render(
        <ProcurementMaterialSourceSettingsClient
          initialConfig={{
            ...initialConfig,
            sync_status: 'syncing',
            sync_phase: 'fetching',
            sync_fetched_count: 0,
            sync_heartbeat_at: staleHeartbeat,
          }}
        />,
      )
    })

    expect(container.textContent).toContain('请求可能已超时，可稍后重试')
  })

  it('shows phase-specific fetched and persisted progress', () => {
    act(() => {
      root.render(
        <ProcurementMaterialSourceSettingsClient
          initialConfig={{
            ...initialConfig,
            sync_status: 'syncing',
            sync_phase: 'persisting',
            sync_fetched_count: 8,
            sync_persisted_count: 5,
          }}
        />,
      )
    })

    expect(container.textContent).toContain('正在写入本地数据库，已读取 8 条')
    expect(container.textContent).toContain('已落库 5 条')
  })

  it('reports an empty Feishu table instead of showing zero progress', () => {
    act(() => {
      root.render(
        <ProcurementMaterialSourceSettingsClient
          initialConfig={{
            ...initialConfig,
            sync_status: 'syncing',
            sync_total_records: 0,
            sync_fetched_count: 0,
          }}
        />,
      )
    })

    expect(container.textContent).toContain('已读取飞书数据，但有效物料为 0 条')
  })

  it('reports an empty sync completion explicitly', async () => {
    vi.useFakeTimers()
    try {
      actions.syncProcurementMaterialSource.mockResolvedValue({
        code: 200,
        message: '采购物料数据同步已启动',
        data: {
          config: { ...initialConfig, sync_status: 'syncing' },
          synced_count: 0,
          deactivated_count: 0,
        },
      })
      materialSourceApi.fetchMaterialSourceConfig.mockResolvedValue({
        code: 200,
        message: 'success',
        data: {
          ...initialConfig,
          sync_status: 'success',
          sync_phase: 'completed',
          sync_total_records: 0,
          sync_fetched_count: 0,
          sync_persisted_count: 0,
          last_sync_record_count: 0,
        },
      })

      act(() => {
        root.render(
          <ProcurementMaterialSourceSettingsClient initialConfig={initialConfig} />,
        )
      })
      const syncButton = Array.from(container.querySelectorAll('button')).find(
        (button) => button.textContent === '同步物料数据',
      )
      await act(async () => {
        syncButton?.click()
        await Promise.resolve()
      })
      await act(async () => {
        await vi.advanceTimersByTimeAsync(MATERIAL_SYNC_POLL_INTERVAL_MS)
      })

      expect(messages.success).toHaveBeenCalledWith(
        '已读取飞书数据，但有效物料为 0 条',
      )
    } finally {
      vi.useRealTimers()
    }
  })

  it('starts a background sync and polls until it completes', async () => {
    vi.useFakeTimers()
    try {
      actions.syncProcurementMaterialSource.mockResolvedValue({
        code: 200,
        message: '采购物料数据同步已启动',
        data: {
          config: {
            ...initialConfig,
            sync_status: 'syncing',
            last_sync_record_count: 18,
          },
          synced_count: 0,
          deactivated_count: 0,
        },
      })
      materialSourceApi.fetchMaterialSourceConfig.mockResolvedValue({
        code: 200,
        message: 'success',
        data: {
          ...initialConfig,
          sync_status: 'success',
          last_sync_record_count: 18,
        },
      })

      act(() => {
        root.render(
          <ProcurementMaterialSourceSettingsClient initialConfig={initialConfig} />,
        )
      })
      const syncButton = Array.from(container.querySelectorAll('button')).find(
        (button) => button.textContent === '同步物料数据',
      )
      await act(async () => {
        syncButton?.click()
        await Promise.resolve()
      })

      expect(actions.syncProcurementMaterialSource).toHaveBeenCalledOnce()
      expect(messages.info).toHaveBeenCalledWith(
        '采购物料数据同步已启动，正在后台同步，请稍候…',
      )
      expect(materialSourceApi.fetchMaterialSourceConfig).not.toHaveBeenCalled()

      await act(async () => {
        await vi.advanceTimersByTimeAsync(MATERIAL_SYNC_POLL_INTERVAL_MS)
      })

      expect(materialSourceApi.fetchMaterialSourceConfig).toHaveBeenCalledOnce()
      expect(messages.success).toHaveBeenCalledWith(
        '采购物料数据同步完成，本地记录 18 条',
      )
      expect(container.textContent).toContain('18')
    } finally {
      vi.useRealTimers()
    }
  })

  it('reports a sync start conflict without polling', async () => {
    actions.syncProcurementMaterialSource.mockResolvedValue({
      code: 409,
      message: '物料数据同步正在进行中，请稍后重试',
      data: null,
    })

    act(() => {
      root.render(<ProcurementMaterialSourceSettingsClient initialConfig={initialConfig} />)
    })
    const syncButton = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent === '同步物料数据',
    )
    await act(async () => {
      syncButton?.click()
      await Promise.resolve()
    })

    expect(messages.error).toHaveBeenCalledWith('物料数据同步正在进行中，请稍后重试')
    expect(materialSourceApi.fetchMaterialSourceConfig).not.toHaveBeenCalled()
  })

  it('reports a sync start failure thrown by the action', async () => {
    actions.syncProcurementMaterialSource.mockRejectedValue(new Error('network'))

    act(() => {
      root.render(<ProcurementMaterialSourceSettingsClient initialConfig={initialConfig} />)
    })
    const syncButton = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent === '同步物料数据',
    )
    await act(async () => {
      syncButton?.click()
      await Promise.resolve()
    })

    expect(messages.error).toHaveBeenCalledWith('采购物料数据同步启动失败，请稍后重试')
  })

  it('warns when syncing without a saved configuration', async () => {
    act(() => {
      root.render(<ProcurementMaterialSourceSettingsClient initialConfig={null} />)
    })
    const syncButton = Array.from(container.querySelectorAll('button')).find(
      (button) => button.textContent === '同步物料数据',
    )
    await act(async () => {
      syncButton?.click()
      await Promise.resolve()
    })

    expect(actions.syncProcurementMaterialSource).not.toHaveBeenCalled()
    expect(messages.warning).toHaveBeenCalledWith('请先保存并测试物料数据源配置')
  })

  it('ignores a non-200 polling response while syncing', async () => {
    vi.useFakeTimers()
    try {
      materialSourceApi.fetchMaterialSourceConfig.mockResolvedValue({
        code: 503,
        message: 'service unavailable',
        data: null,
      })

      act(() => {
        root.render(
          <ProcurementMaterialSourceSettingsClient
            initialConfig={{ ...initialConfig, sync_status: 'syncing' }}
          />,
        )
      })
      await act(async () => {
        await vi.advanceTimersByTimeAsync(MATERIAL_SYNC_POLL_INTERVAL_MS)
      })

      expect(materialSourceApi.fetchMaterialSourceConfig).toHaveBeenCalledOnce()
      expect(messages.success).not.toHaveBeenCalled()
      expect(messages.error).not.toHaveBeenCalled()
    } finally {
      vi.useRealTimers()
    }
  })

  it('keeps polling after a transient poll failure', async () => {
    vi.useFakeTimers()
    try {
      actions.syncProcurementMaterialSource.mockResolvedValue({
        code: 200,
        message: '采购物料数据同步已启动',
        data: {
          config: { ...initialConfig, sync_status: 'syncing' },
          synced_count: 0,
          deactivated_count: 0,
        },
      })
      materialSourceApi.fetchMaterialSourceConfig
        .mockRejectedValueOnce(new Error('network'))
        .mockResolvedValueOnce({
          code: 200,
          message: 'success',
          data: { ...initialConfig, sync_status: 'success' },
        })

      act(() => {
        root.render(<ProcurementMaterialSourceSettingsClient initialConfig={initialConfig} />)
      })
      const syncButton = Array.from(container.querySelectorAll('button')).find(
        (button) => button.textContent === '同步物料数据',
      )
      await act(async () => {
        syncButton?.click()
        await Promise.resolve()
      })

      await act(async () => {
        await vi.advanceTimersByTimeAsync(MATERIAL_SYNC_POLL_INTERVAL_MS)
      })
      await act(async () => {
        await vi.advanceTimersByTimeAsync(MATERIAL_SYNC_POLL_INTERVAL_MS)
      })

      expect(materialSourceApi.fetchMaterialSourceConfig).toHaveBeenCalledTimes(2)
      expect(messages.success).toHaveBeenCalledWith(
        '采购物料数据同步完成，本地记录 12 条',
      )
    } finally {
      vi.useRealTimers()
    }
  })

  it('reports a failed sync status returned by polling', async () => {
    vi.useFakeTimers()
    try {
      actions.syncProcurementMaterialSource.mockResolvedValue({
        code: 200,
        message: '采购物料数据同步已启动',
        data: {
          config: { ...initialConfig, sync_status: 'syncing' },
          synced_count: 0,
          deactivated_count: 0,
        },
      })
      materialSourceApi.fetchMaterialSourceConfig.mockResolvedValue({
        code: 200,
        message: 'success',
        data: {
          ...initialConfig,
          sync_status: 'error',
          sync_error: '飞书多维表格请求超时',
        },
      })

      act(() => {
        root.render(<ProcurementMaterialSourceSettingsClient initialConfig={initialConfig} />)
      })
      const syncButton = Array.from(container.querySelectorAll('button')).find(
        (button) => button.textContent === '同步物料数据',
      )
      await act(async () => {
        syncButton?.click()
        await Promise.resolve()
      })
      await act(async () => {
        await vi.advanceTimersByTimeAsync(MATERIAL_SYNC_POLL_INTERVAL_MS)
      })

      expect(messages.error).toHaveBeenCalledWith('飞书多维表格请求超时')
    } finally {
      vi.useRealTimers()
    }
  })
})
