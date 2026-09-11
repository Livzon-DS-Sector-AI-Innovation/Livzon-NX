/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const registrationActions = vi.hoisted(() => ({
  updateCertificateReminderSettings: vi.fn(),
  testCertificateReminderSettings: vi.fn(),
}))

const regulatoryActions = vi.hoisted(() => ({
  testRegulatoryTrackerNotificationSettings: vi.fn(),
}))

const regulatoryClient = vi.hoisted(() => ({
  fetchRegulatoryTrackerNotificationRecipientsClient: vi.fn(),
  updateRegulatoryTrackerNotificationSettingsClient: vi.fn(),
}))

const nextNavigation = vi.hoisted(() => ({
  useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }),
}))

vi.mock('@/actions/registration', () => registrationActions)
vi.mock('@/actions/regulatory-tracker', () => regulatoryActions)
vi.mock('@/lib/api/client/regulatoryTracker', () => regulatoryClient)
vi.mock('next/navigation', () => nextNavigation)

import { RegistrationSettingsPage } from './RegistrationSettingsPage'

const REMINDER_SETTINGS = {
  is_enabled: true,
  reminder_days: 90,
  recipient_open_id: 'ou_zqz',
  recipient_name: '张起智',
  recipient_department: 'QA部',
  pending_count: 3,
  header_template: null as string | null,
  footer_template: null as string | null,
}

const REMINDER_RECIPIENTS = [
  { open_id: 'ou_zqz', name: '张起智', department: 'QA部', enterprise_email: null },
]

const NOTIFICATION_SETTINGS = {
  is_enabled: true,
  recent_days: 7,
  recipient_open_id: 'ou_zqz',
  recipient_name: '张起智',
  recipient_department: 'QA部',
  schedule_time: '10:00',
  pending_count: 2,
  header_template: '自定义法规开头 {count}' as string | null,
  footer_template: null as string | null,
}

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
}

describe('RegistrationSettingsPage', () => {
  let root: Root
  let container: HTMLElement

  beforeEach(() => {
    registrationActions.updateCertificateReminderSettings.mockResolvedValue({
      ...REMINDER_SETTINGS,
    })
    registrationActions.testCertificateReminderSettings.mockResolvedValue({
      sent: true,
      recipient_name: '张起智',
      detail: '测试消息已发送至 张起智',
    })
    regulatoryClient.fetchRegulatoryTrackerNotificationRecipientsClient.mockResolvedValue(
      REMINDER_RECIPIENTS,
    )
    regulatoryActions.testRegulatoryTrackerNotificationSettings.mockResolvedValue({
      sent: true,
      recipient_name: '张起智',
      detail: '测试消息已发送至 张起智',
    })
    regulatoryClient.updateRegulatoryTrackerNotificationSettingsClient.mockResolvedValue({
      ...NOTIFICATION_SETTINGS,
    })
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    document.body
      .querySelectorAll('.ant-modal-root, .ant-select-dropdown, .ant-message')
      .forEach((node) => node.remove())
    vi.clearAllMocks()
  })

  async function renderPage() {
    act(() => {
      root.render(
        <QueryClientProvider client={makeQueryClient()}>
          <App>
            <RegistrationSettingsPage
              reminderSettings={{ ...REMINDER_SETTINGS }}
              reminderRecipients={REMINDER_RECIPIENTS}
              notificationSettings={{ ...NOTIFICATION_SETTINGS }}
              notificationRecipients={REMINDER_RECIPIENTS}
            />
          </App>
        </QueryClientProvider>,
      )
    })
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 60))
    })
  }

  function findButton(text: string, index = 0) {
    const matches = Array.from(container.querySelectorAll('button')).filter(
      (btn) => btn.textContent?.includes(text),
    )
    return matches[index]
  }

  it('renders both notification cards with configured values', async () => {
    await renderPage()
    const text = container.textContent || ''
    expect(text).toContain('注册设置')
    expect(text).toContain('通知设置')
    expect(text).toContain('证书到期提醒设置')
    expect(text).toContain('法规更新推送设置')
    expect(text).toContain('命中 3 份待提醒证书')
    expect(text).toContain('执行时间：每日 10:00')
    expect(text).toContain('命中 2 条待推送更新')
    expect(text).toContain('当前通知人：张起智 / QA部')
    expect(text).toContain('消息模板（开头语 / 结尾语）')
  })

  it('saves certificate reminder settings with template draft values', async () => {
    await renderPage()
    const saveButton = findButton('保存设置', 0)
    expect(saveButton).toBeTruthy()
    await act(async () => {
      saveButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 60))
    })
    expect(
      registrationActions.updateCertificateReminderSettings,
    ).toHaveBeenCalledWith(
      expect.objectContaining({
        is_enabled: true,
        reminder_days: 90,
        recipient_open_id: 'ou_zqz',
        header_template: null,
        footer_template: null,
      }),
    )
  })

  it('sends certificate reminder test message to selected recipient', async () => {
    await renderPage()
    const testButton = findButton('测试发送', 0)
    expect(testButton).toBeTruthy()
    await act(async () => {
      testButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 60))
    })
    expect(
      registrationActions.testCertificateReminderSettings,
    ).toHaveBeenCalledWith({
      recipient_open_id: 'ou_zqz',
      header_template: null,
      footer_template: null,
    })
    expect(document.body.textContent).toContain('测试消息已发送至 张起智')
  })

  it('sends regulation push test message with saved template', async () => {
    await renderPage()
    const testButton = findButton('测试发送', 1)
    expect(testButton).toBeTruthy()
    await act(async () => {
      testButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 60))
    })
    expect(
      regulatoryActions.testRegulatoryTrackerNotificationSettings,
    ).toHaveBeenCalledWith({
      recipient_open_id: 'ou_zqz',
      header_template: '自定义法规开头 {count}',
      footer_template: null,
    })
  })

  it('saves regulation push settings carrying template fields', async () => {
    await renderPage()
    const saveButton = findButton('保存设置', 1)
    expect(saveButton).toBeTruthy()
    await act(async () => {
      saveButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 60))
    })
    expect(
      regulatoryClient.updateRegulatoryTrackerNotificationSettingsClient,
    ).toHaveBeenCalledWith(
      expect.objectContaining({
        is_enabled: true,
        recent_days: 7,
        recipient_open_id: 'ou_zqz',
        header_template: '自定义法规开头 {count}',
        footer_template: null,
      }),
    )
  })

  it('surfaces test-send failure detail as warning', async () => {
    regulatoryActions.testRegulatoryTrackerNotificationSettings.mockResolvedValue(
      {
        sent: false,
        recipient_name: '张起智',
        detail: '质量模块飞书应用未配置或已停用，无法发送测试消息',
      },
    )
    await renderPage()
    const testButton = findButton('测试发送', 1)
    await act(async () => {
      testButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 60))
    })
    expect(document.body.textContent).toContain(
      '质量模块飞书应用未配置或已停用，无法发送测试消息',
    )
  })
})
