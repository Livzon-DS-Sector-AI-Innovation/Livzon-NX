/* @vitest-environment happy-dom */

import { act, createElement, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  getSafetyFeishuSettings: vi.fn(),
  saveSafetyFeishuSettings: vi.fn(),
  testSafetyFeishuSettings: vi.fn(),
  getSafetyFeishuWsStatus: vi.fn(),
  restartSafetyFeishuWs: vi.fn(),
  testRadarNotify: vi.fn(),
}))

vi.mock('@/actions/safety', () => ({
  getSafetyFeishuSettings: mocks.getSafetyFeishuSettings,
  saveSafetyFeishuSettings: mocks.saveSafetyFeishuSettings,
  testSafetyFeishuSettings: mocks.testSafetyFeishuSettings,
  testRadarNotify: mocks.testRadarNotify,
  getSafetyFeishuWsStatus: mocks.getSafetyFeishuWsStatus,
  restartSafetyFeishuWs: mocks.restartSafetyFeishuWs,
}))

vi.mock('@/components/shared/PlatformNotice', async () => {
  const { createElement } = await import('react')
  return {
    default: ({ title }: { title?: ReactNode }) =>
      createElement('div', { 'data-notice': 'true' }, title as ReactNode),
  }
})

vi.mock('@ant-design/icons', () => {
  const Icon = () => null
  return {
    ApiOutlined: Icon,
    SecurityScanOutlined: Icon,
    SaveOutlined: Icon,
    SendOutlined: Icon,
  }
})

vi.mock('antd', async () => {
  const { createElement } = await import('react')

  type AnyProps = Record<string, unknown> & { children?: ReactNode }
  type ChangeHandler = ((event: { target: { value: string } }) => void) | undefined
  type CheckedHandler = ((checked: boolean) => void) | undefined

  const Box = ({ children, title, extra }: AnyProps) =>
    createElement('div', null, title as ReactNode, extra as ReactNode, children as ReactNode)
  const Text = ({ children }: AnyProps) => createElement('span', null, children as ReactNode)
  const Button = ({ children, onClick, disabled }: AnyProps) =>
    createElement(
      'button',
      { type: 'button', disabled: Boolean(disabled), onClick: onClick as never },
      children as ReactNode
    )
  // happy-dom 下 React 19 收不到原生 input/change 合成事件，这里用 ref 把 DOM
  // 事件直接接到组件回调，保证受控输入交互真实生效。
  const textInput = (props: AnyProps, extra: Record<string, unknown> = {}) => {
    const { value, onChange, placeholder } = props
    return createElement('input', {
      value: (value as string) ?? '',
      placeholder: placeholder as string,
      ref: (node: HTMLInputElement | null) => {
        if (!node) return
        node.onchange = () =>
          (onChange as ChangeHandler)?.({ target: { value: node.value } })
      },
      ...extra,
    })
  }
  const Input = Object.assign((props: AnyProps) => textInput(props), {
    Password: (props: AnyProps) => textInput(props, { type: 'password' }),
  })
  const Switch = ({ checked, onChange }: AnyProps) =>
    createElement('input', {
      type: 'checkbox',
      checked: Boolean(checked),
      ref: (node: HTMLInputElement | null) => {
        if (!node) return
        node.onchange = () => (onChange as CheckedHandler)?.(node.checked)
      },
    })

  return {
    App: { useApp: () => ({ message: mocks.message }) },
    Button,
    Card: Box,
    Tabs: ({ items }: { items?: { key: string; children?: ReactNode }[] }) =>
      createElement(
        'div',
        null,
        ...((items ?? []) as { key: string; children?: ReactNode }[]).map((item) =>
          createElement('div', { key: item.key }, item.children)
        ),
      ),
    Input,
    Space: Object.assign(Box, { Compact: Box }),
    Switch,
    Tag: Text,
    Typography: { Text, Title: Text },
  }
})

import FeishuSettingsPage from './FeishuSettingsPage'

const settingsDetail = {
  app_id: 'cli_safety',
  app_secret_masked: '****abcd',
  is_enabled: true,
  bitable_app_token: 'bascnToken',
  bitable_hazard_table_id: 'tblHazard',
  knowledge_app_token: 'bascnKnowledge',
  knowledge_table_id: 'tblKnowledge',
  last_test_status: 'success',
  last_tested_at: '2026-10-01T02:00:00.000Z',
  last_test_error: null,
  knowledge_last_sync_status: 'partial',
  knowledge_last_synced_at: '2026-10-02T03:00:00.000Z',
  knowledge_last_sync_error: '2 条记录同步失败',
}

let rendered: { root: Root; container: HTMLDivElement } | undefined

function renderPage(props: {
  initialSettings?: Record<string, unknown> | null
  initialWsStatus?: Record<string, unknown> | null
}) {
  const container = document.createElement('div')
  document.body.append(container)
  const root = createRoot(container)
  act(() => {
    root.render(
      createElement(FeishuSettingsPage, {
        initialSettings: (props.initialSettings ?? null) as never,
        initialWsStatus: props.initialWsStatus ?? null,
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

function findInput(container: HTMLElement, placeholder: string): HTMLInputElement | undefined {
  return Array.from(container.querySelectorAll('input')).find((input) =>
    input.placeholder?.includes(placeholder)
  ) as HTMLInputElement | undefined
}

function setInput(container: HTMLElement, placeholder: string, value: string) {
  const input = findInput(container, placeholder)
  if (!input) return
  input.value = value
  input.dispatchEvent(new Event('change', { bubbles: true }))
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.getSafetyFeishuSettings.mockResolvedValue({ code: 200, data: settingsDetail })
  mocks.getSafetyFeishuWsStatus.mockResolvedValue({ code: 200, data: { connected: true } })
  mocks.saveSafetyFeishuSettings.mockResolvedValue({ code: 200, data: settingsDetail })
  mocks.testRadarNotify.mockResolvedValue({ code: 200, data: { sent: 2, errors: [] } })
})

afterEach(() => {
  if (rendered) {
    act(() => rendered?.root.unmount())
    rendered.container.remove()
    rendered = undefined
  }
})

describe('FeishuSettingsPage interactions', () => {
  it('renders 已保存凭证、连接与同步标签、已连接事件列表', async () => {
    rendered = renderPage({
      initialSettings: settingsDetail,
      initialWsStatus: { connected: true, registered_events: ['hazard.updated', 'card.action'] },
    })
    await settle()

    const markup = rendered.container.innerHTML
    expect(markup).toContain('连接正常')
    expect(markup).toContain('部分失败')
    expect(markup).toContain('已连接')
    expect(markup).toContain('已注册事件：hazard.updated、card.action')
    expect(markup).toContain('2 条记录同步失败')
    expect(markup).toContain('****abcd')
    expect(findInput(rendered.container, 'App ID')?.value).toBe('cli_safety')
    expect(findInput(rendered.container, 'bascn 开头')?.value).toBe('bascnToken')
  })

  it('renders 未测试/同步失败状态，兼容 event_types 与未同步标签', async () => {
    rendered = renderPage({
      initialSettings: {
        app_id: 'cli_safety',
        last_test_status: 'failed',
        last_test_error: 'App Secret 无效',
        last_tested_at: 'not-a-date',
        knowledge_last_sync_status: 'failed',
        knowledge_last_sync_error: '同步失败',
        knowledge_last_synced_at: null,
      },
      initialWsStatus: { running: true, event_types: [] },
    })
    await settle()

    const markup = rendered.container.innerHTML
    expect(markup).toContain('连接失败')
    expect(markup).toContain('同步失败')
    expect(markup).toContain('已注册事件：无')
    expect(markup).toContain('未测试')
  })

  it('renders 未连接与未同步分支', async () => {
    // running/connected/is_connected 全为假 → 未连接提示；无配置行 → 未同步标签
    rendered = renderPage({
      initialSettings: null,
      initialWsStatus: { connected: false, is_connected: false, running: false },
    })
    await settle()

    const markup = rendered.container.innerHTML
    expect(markup).toContain('未连接时隐患表格变更不会同步')
    expect(markup).toContain('未连接')
    expect(markup).toContain('未同步')
    expect(markup).toContain('留空则保持当前 Secret 不变')
  })

  it('warns when app id or first-time secret is missing', async () => {
    rendered = renderPage({ initialSettings: null, initialWsStatus: null })
    await settle()

    act(() => findButton(rendered!.container, '保存配置')?.click())
    await settle()
    expect(mocks.message.warning).toHaveBeenCalledWith('请填写飞书应用 App ID')

    setInput(rendered.container, 'App ID', 'cli_new')
    await settle()
    expect(findInput(rendered.container, 'App ID')?.value).toBe('cli_new')

    act(() => findButton(rendered!.container, '保存配置')?.click())
    await settle()
    expect(mocks.message.warning).toHaveBeenCalledWith('首次保存需要填写 App Secret')
  })

  it('saves credentials, clears the secret field and reports failures', async () => {
    mocks.saveSafetyFeishuSettings.mockResolvedValue({ code: 200, data: settingsDetail })
    rendered = renderPage({ initialSettings: null, initialWsStatus: null })
    await settle()

    setInput(rendered.container, 'App ID', 'cli_new')
    setInput(rendered.container, '留空则保持当前 Secret 不变', 'super-secret')
    await settle()

    act(() => findButton(rendered!.container, '保存配置')?.click())
    await settle()
    expect(mocks.saveSafetyFeishuSettings).toHaveBeenCalledWith(
      expect.objectContaining({ app_id: 'cli_new', app_secret: 'super-secret' })
    )
    expect(mocks.message.success).toHaveBeenCalledWith('飞书配置已保存')
    expect(findInput(rendered.container, '****abcd')?.value ?? '').toBe('')

    mocks.saveSafetyFeishuSettings.mockResolvedValueOnce({ code: 500, message: '密钥无法解密' })
    act(() => findButton(rendered!.container, '保存配置')?.click())
    await settle()
    expect(mocks.message.error).toHaveBeenCalledWith('密钥无法解密')
  })

  it('tests the connection and refreshes stored status', async () => {
    mocks.testSafetyFeishuSettings.mockResolvedValueOnce({
      code: 200,
      data: { success: true, message: '连接成功' },
    })
    rendered = renderPage({ initialSettings: settingsDetail, initialWsStatus: null })
    await settle()

    act(() => findButton(rendered!.container, '测试连接')?.click())
    await settle()
    expect(mocks.message.success).toHaveBeenCalledWith('连接成功')
    expect(mocks.getSafetyFeishuSettings).toHaveBeenCalled()

    mocks.testSafetyFeishuSettings.mockResolvedValueOnce({
      code: 200,
      data: { success: false, message: 'App ID 不存在' },
    })
    act(() => findButton(rendered!.container, '测试连接')?.click())
    await settle()
    expect(mocks.message.error).toHaveBeenCalledWith('App ID 不存在')

    mocks.testSafetyFeishuSettings.mockResolvedValueOnce({ code: 500, message: '后端不可用' })
    act(() => findButton(rendered!.container, '测试连接')?.click())
    await settle()
    expect(mocks.message.error).toHaveBeenCalledWith('后端不可用')
  })

  it('restarts the websocket subscription and refreshes its status', async () => {
    mocks.restartSafetyFeishuWs.mockResolvedValueOnce({ code: 200, data: { ok: true } })
    mocks.getSafetyFeishuWsStatus.mockResolvedValueOnce({
      code: 200,
      data: { running: true, registered_events: ['hazard.updated'] },
    })
    rendered = renderPage({ initialSettings: settingsDetail, initialWsStatus: null })
    await settle()
    expect(rendered.container.innerHTML).toContain('未连接')

    act(() => findButton(rendered!.container, '重连事件订阅')?.click())
    await settle()
    expect(mocks.message.success).toHaveBeenCalledWith('已重新发起飞书事件订阅连接')
    expect(rendered.container.innerHTML).toContain('已连接')

    mocks.restartSafetyFeishuWs.mockResolvedValueOnce({ code: 500, message: 'WS 启动失败' })
    act(() => findButton(rendered!.container, '重连事件订阅')?.click())
    await settle()
    expect(mocks.message.error).toHaveBeenCalledWith('WS 启动失败')
  })

  it('keeps edited bindings and the enable switch in the save payload', async () => {
    mocks.saveSafetyFeishuSettings.mockResolvedValue({ code: 200, data: settingsDetail })
    rendered = renderPage({ initialSettings: settingsDetail, initialWsStatus: null })
    await settle()

    setInput(rendered.container, 'EHS 法规库多维表格 app_token', 'bascnNew')
    const switchInput = rendered.container.querySelector(
      'input[type="checkbox"]'
    ) as HTMLInputElement
    act(() => {
      switchInput.checked = false
      switchInput.dispatchEvent(new Event('change', { bubbles: true }))
    })
    await settle()

    act(() => findButton(rendered!.container, '保存配置')?.click())
    await settle()
    expect(mocks.saveSafetyFeishuSettings).toHaveBeenCalledWith(
      expect.objectContaining({ knowledge_app_token: 'bascnNew', is_enabled: false })
    )
  })

  it('keeps radar notify targets in the save payload', async () => {
    rendered = renderPage({ initialSettings: settingsDetail, initialWsStatus: null })
    await settle()

    setInput(rendered.container, '飞书群 chat_id', 'oc_group1, oc_group2')
    setInput(rendered.container, '个人 open_id', 'ou_group9')
    const switches = Array.from(
      rendered.container.querySelectorAll('input[type="checkbox"]')
    ) as HTMLInputElement[]
    // 页面共两个开关：0=启用飞书集成，1=启用扫描结果通知
    const notifySwitch = switches[1]
    act(() => {
      notifySwitch.checked = true
      notifySwitch.dispatchEvent(new Event('change', { bubbles: true }))
    })
    await settle()

    act(() => findButton(rendered!.container, '保存配置')?.click())
    await settle()

    const payload = mocks.saveSafetyFeishuSettings.mock.calls.at(-1)?.[0] as {
      radar_notify_enabled?: boolean
      radar_notify_chat_ids?: string[]
      radar_notify_user_ids?: string[]
    }
    expect(payload.radar_notify_enabled).toBe(true)
    expect(payload.radar_notify_chat_ids).toEqual(['oc_group1', 'oc_group2'])
    expect(payload.radar_notify_user_ids).toEqual(['ou_group9'])
  })

  it('sends a radar notify test after saving the current targets', async () => {
    rendered = renderPage({ initialSettings: settingsDetail, initialWsStatus: null })
    await settle()

    act(() => findButton(rendered!.container, '发送测试通知')?.click())
    await settle()

    expect(mocks.saveSafetyFeishuSettings).toHaveBeenCalled()
    expect(mocks.testRadarNotify).toHaveBeenCalled()
    expect(mocks.message.success).toHaveBeenCalledWith('测试通知已发送（2 个目标）')

    // 无有效目标：sent=0 时展示后端错误明细
    mocks.testRadarNotify.mockResolvedValueOnce({ code: 200, data: { sent: 0, errors: ['未配置通知目标'] } })
    act(() => findButton(rendered!.container, '发送测试通知')?.click())
    await settle()
    expect(mocks.message.error).toHaveBeenCalledWith('未配置通知目标')

    // 接口失败分支
    mocks.testRadarNotify.mockResolvedValueOnce({ code: 500, message: '飞书不可用' })
    act(() => findButton(rendered!.container, '发送测试通知')?.click())
    await settle()
    expect(mocks.message.error).toHaveBeenCalledWith('飞书不可用')

    // 保存失败时不再发测试通知
    mocks.saveSafetyFeishuSettings.mockResolvedValueOnce({ code: 500, message: '凭证无效' })
    act(() => findButton(rendered!.container, '发送测试通知')?.click())
    await settle()
    expect(mocks.message.error).toHaveBeenCalledWith('凭证无效')
  })

  it('requires app id before sending a radar notify test', async () => {
    rendered = renderPage({
      initialSettings: { ...settingsDetail, app_id: '' },
      initialWsStatus: null,
    })
    await settle()

    setInput(rendered.container, 'App ID', '')
    act(() => findButton(rendered!.container, '发送测试通知')?.click())
    await settle()

    expect(mocks.testRadarNotify).not.toHaveBeenCalled()
    expect(mocks.message.warning).toHaveBeenCalledWith('请先填写飞书应用 App ID')
  })
})