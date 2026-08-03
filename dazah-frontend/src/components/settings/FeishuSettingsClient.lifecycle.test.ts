import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const lifecycle = vi.hoisted(() => ({
  effects: [] as Array<() => void | (() => void)>,
  setters: [] as Array<ReturnType<typeof vi.fn>>,
}))

const ui = vi.hoisted(() => {
  const form = {
    setFieldsValue: vi.fn(),
    setFieldValue: vi.fn(),
    validateFields: vi.fn(),
  }
  const bindingForm = {
    setFieldsValue: vi.fn(),
    resetFields: vi.fn(),
  }
  return {
    form,
    bindingForm,
    formIndex: 0,
    message: {
      error: vi.fn(),
      success: vi.fn(),
      warning: vi.fn(),
    },
  }
})

const actions = vi.hoisted(() => ({
  createExternalIdentityBinding: vi.fn(),
  disableExternalIdentityBinding: vi.fn(),
  getAgentToolCatalog: vi.fn(),
  getExternalIdentityBindings: vi.fn(),
  getLivzonFeishuConfig: vi.fn(),
  getLivzonFeishuGatewayStatus: vi.fn(),
  setAgentToolEnabled: vi.fn(),
}))

vi.mock('react', async (importOriginal) => {
  const original = await importOriginal<typeof import('react')>()
  return {
    ...original,
    useEffect: vi.fn((effect: () => void | (() => void)) => {
      lifecycle.effects.push(effect)
    }),
    useState: vi.fn((initial: unknown) => {
      const setter = vi.fn()
      lifecycle.setters.push(setter)
      return [initial, setter]
    }),
  }
})

vi.mock('antd', () => {
  const FormItem = () => null
  const Form = Object.assign(() => null, {
    Item: FormItem,
    useForm: vi.fn(() => [
      ui.formIndex++ === 0 ? ui.form : ui.bindingForm,
    ]),
  })
  const ListMeta = () => null
  const ListItem = Object.assign(() => null, { Meta: ListMeta })
  const List = Object.assign(() => null, { Item: ListItem })
  return {
    App: { useApp: () => ({ message: ui.message }) },
    Button: () => null,
    Card: () => null,
    Form,
    Input: () => null,
    List,
    Space: () => null,
    Switch: () => null,
    Tag: () => null,
    Typography: { Text: () => null, Title: () => null },
  }
})

vi.mock('@/actions/settings', () => actions)

import FeishuSettingsClient from './FeishuSettingsClient'

interface ElementLike {
  props?: Record<string, unknown>
}

function walk(node: ReactNode | unknown): ElementLike[] {
  if (Array.isArray(node)) {
    return node.flatMap(walk)
  }
  if (typeof node !== 'object' || node === null) {
    return []
  }
  const element = node as ElementLike
  return [
    element,
    ...walk(element.props?.children),
  ]
}

function textOf(node: unknown): string {
  if (typeof node === 'string' || typeof node === 'number') {
    return String(node)
  }
  if (Array.isArray(node)) {
    return node.map(textOf).join('')
  }
  if (typeof node === 'object' && node !== null) {
    return textOf((node as ElementLike).props?.children)
  }
  return ''
}

describe('FeishuSettingsClient lifecycle', () => {
  beforeEach(() => {
    lifecycle.effects.length = 0
    lifecycle.setters.length = 0
    ui.formIndex = 0
    vi.clearAllMocks()
    actions.getLivzonFeishuConfig.mockResolvedValue({
      id: null,
      config_name: 'Livzon',
      app_id: 'cli_app',
      tenant_id: 'tenant-a',
      gateway_enabled: true,
      config_version: 3,
      app_secret_configured: true,
      app_secret_masked: '***',
      is_active: true,
    })
    actions.getLivzonFeishuGatewayStatus.mockResolvedValue({
      gateway: 'connected',
      config_version: 3,
      gateway_reconnects: 0,
    })
    actions.getExternalIdentityBindings.mockResolvedValue([
      { id: 'binding-1', status: 'active' },
    ])
    actions.getAgentToolCatalog.mockResolvedValue([
      { operation: 'quality.create_deviation', status: 'active' },
    ])
    ui.form.validateFields.mockResolvedValue({
      app_id: 'cli_app',
      app_secret: '',
      tenant_id: 'tenant-a',
      gateway_enabled: true,
    })
  })

  it('loads control-plane state and executes management handlers', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            data: {
              app_id: 'cli_app',
              tenant_id: 'tenant-a',
              gateway_enabled: true,
            },
          }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            data: {
              steps: [{ name: 'tenant_access_token', status: 'ok' }],
            },
          }),
          { status: 200 },
        ),
      )
    vi.stubGlobal('fetch', fetchMock)

    const tree = FeishuSettingsClient()
    expect(lifecycle.effects).toHaveLength(1)
    const cleanup = lifecycle.effects[0]()

    await vi.waitFor(() => {
      expect(ui.form.setFieldsValue).toHaveBeenCalled()
      expect(ui.bindingForm.setFieldsValue).toHaveBeenCalled()
      expect(lifecycle.setters[0]).toHaveBeenCalled()
      expect(lifecycle.setters[4]).toHaveBeenCalled()
      expect(lifecycle.setters[5]).toHaveBeenCalled()
      expect(lifecycle.setters[6]).toHaveBeenCalled()
    })

    const elements = walk(tree)
    const buttons = elements.filter(
      (element) => typeof element.props?.onClick === 'function',
    )
    const save = buttons.find((element) => textOf(element).includes('保存凭证'))
    const test = buttons.find((element) => textOf(element).includes('测试连通性'))
    expect(save).toBeDefined()
    expect(test).toBeDefined()
    await (save?.props?.onClick as () => Promise<void>)()
    await (test?.props?.onClick as () => Promise<void>)()

    const bindingForm = elements.find(
      (element) => typeof element.props?.onFinish === 'function',
    )
    await (
      bindingForm?.props?.onFinish as (
        values: Record<string, unknown>,
      ) => Promise<void>
    )({
      tenant_id: 'tenant-a',
      app_fingerprint: 'cli_app',
      external_open_id: 'ou_user',
      local_user_id: '00000000-0000-0000-0000-000000000001',
    })
    expect(actions.createExternalIdentityBinding).toHaveBeenCalled()
    expect(ui.bindingForm.resetFields).toHaveBeenCalled()

    const lists = elements.filter(
      (element) => typeof element.props?.renderItem === 'function',
    )
    expect(lists).toHaveLength(2)
    const bindingItem = (
      lists[0].props?.renderItem as (item: Record<string, unknown>) => ReactNode
    )({
      id: 'binding-1',
      status: 'active',
      tenant_id: 'tenant-a',
      app_fingerprint: 'cli_app',
      external_open_id: 'ou_user',
      local_user_id: '00000000-0000-0000-0000-000000000001',
    })
    const disable = walk(
      (bindingItem as ElementLike).props?.actions,
    ).find(
      (element) => typeof element.props?.onClick === 'function',
    )
    await (disable?.props?.onClick as () => Promise<void>)()
    expect(actions.disableExternalIdentityBinding).toHaveBeenCalledWith(
      'binding-1',
    )

    const toolItem = (
      lists[1].props?.renderItem as (item: Record<string, unknown>) => ReactNode
    )({
      operation: 'quality.create_deviation',
      module: 'quality',
      summary: '创建偏差',
      status: 'active',
      risk_level: 'high',
    })
    const toggle = walk(
      (toolItem as ElementLike).props?.actions,
    ).find(
      (element) => typeof element.props?.onChange === 'function',
    )
    await (toggle?.props?.onChange as (enabled: boolean) => Promise<void>)(false)
    expect(actions.setAgentToolEnabled).toHaveBeenCalledWith(
      'quality.create_deviation',
      false,
    )

    expect(ui.message.success).toHaveBeenCalledWith(
      'Livzon 助手凭证连通性测试通过',
    )
    expect(typeof cleanup).toBe('function')
    cleanup?.()
    vi.unstubAllGlobals()
  })
})
