/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const qualityActions = vi.hoisted(() => ({
  fetchQualityNotificationSettings: vi.fn(),
  updateQualityNotificationSetting: vi.fn(),
}))

const apiClient = vi.hoisted(() => ({
  searchChangeActionPlanPersons: vi.fn(),
  searchQualityPersonOptions: vi.fn(),
  fetchQaPersonOptions: vi.fn(),
}))

vi.mock('@/hooks/usePagePermissions', () => ({
  usePagePermissions: () => ({ canSync: true }),
}))

vi.mock('@/actions/quality', () => qualityActions)
vi.mock('@/lib/api/client/quality', () => apiClient)

import { QualityNotificationSettingsPanel } from './QualityNotificationSettingsPanel'

const SETTINGS = [
  {
    notification_type: 'change_action_plan_due',
    notification_label: '变更计划到期提醒',
    is_enabled: true,
    lead_days: 3,
    repeat_interval_days: 1,
    send_time: '09:00',
    fallback_recipients: [{ open_id: 'ou_fb', name: '兜底人' }],
    inspection_lines: [],
  },
  {
    notification_type: 'inspection_trend_alert',
    notification_label: '成品检验趋势异常提醒',
    is_enabled: true,
    lead_days: 3,
    repeat_interval_days: 1,
    send_time: '09:00',
    fallback_recipients: [],
    inspection_lines: [
      {
        entity_code: 'qc_finished_internal',
        entity_label: '霉酚酸（内控）',
        enabled: true,
        recipients: [{ open_id: 'ou_lp', name: '陈连平' }],
      },
      {
        entity_code: 'qc_finished_pure_water',
        entity_label: '纯化水',
        enabled: true,
        recipients: [],
      },
    ],
  },
  {
    notification_type: 'inspection_trend_alert_escalation',
    notification_label: '成品/纯化水异常升级推送',
    is_enabled: true,
    lead_days: 3,
    repeat_interval_days: 1,
    send_time: '09:00',
    fallback_recipients: [],
    inspection_lines: [],
    first_recipients: [],
    escalation_hours: 3,
  },
]

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
}

describe('QualityNotificationSettingsPanel', () => {
  let root: Root
  let container: HTMLElement

  beforeEach(() => {
    qualityActions.fetchQualityNotificationSettings.mockResolvedValue(
      SETTINGS.map((item) => structuredClone(item)),
    )
    qualityActions.updateQualityNotificationSetting.mockResolvedValue({
      ...SETTINGS[0],
      is_enabled: false,
    })
    apiClient.searchChangeActionPlanPersons.mockResolvedValue([])
    apiClient.searchQualityPersonOptions.mockResolvedValue([])
    apiClient.fetchQaPersonOptions.mockResolvedValue([])
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

  async function renderPanel() {
    act(() => {
      root.render(
        <QueryClientProvider client={makeQueryClient()}>
          <App>
            <QualityNotificationSettingsPanel />
          </App>
        </QueryClientProvider>,
      )
    })
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 60))
    })
  }

  it('renders both notification cards with configured values', async () => {
    await renderPanel()
    const text = container.textContent || ''
    expect(text).toContain('变更计划到期提醒')
    expect(text).toContain('成品检验趋势异常提醒')
    expect(text).toContain('兜底人')
    expect(text).toContain('霉酚酸（内控）')
    expect(text).toContain('纯化水')
    expect(text).toContain('每天发送时间')
    expect(text).toContain('重复间隔')
  })

  it('saves change action plan due settings with current draft values', async () => {
    await renderPanel()
    const saveButton = Array.from(container.querySelectorAll('button')).find(
      (btn) => /保\s*存/.test(btn.textContent || ''),
    )
    expect(saveButton).toBeTruthy()
    await act(async () => {
      saveButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 60))
    })
    expect(qualityActions.updateQualityNotificationSetting).toHaveBeenCalledWith(
      'change_action_plan_due',
      expect.objectContaining({
        is_enabled: true,
        lead_days: 3,
        repeat_interval_days: 1,
        send_time: '09:00',
        fallback_recipients: [{ open_id: 'ou_fb', name: '兜底人' }],
      }),
    )
  })

  it('toggles inspection global switch and saves with disabled flag', async () => {
    await renderPanel()
    const switches = Array.from(container.querySelectorAll('button.ant-switch'))
    // 第 1 个是变更计划卡开关，第 2 个是检验卡总开关
    expect(switches.length).toBeGreaterThanOrEqual(2)
    qualityActions.updateQualityNotificationSetting.mockResolvedValue({
      ...SETTINGS[1],
      is_enabled: false,
    })
    await act(async () => {
      switches[1].dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    const saveButtons = Array.from(container.querySelectorAll('button')).filter(
      (btn) => /保\s*存/.test(btn.textContent || ''),
    )
    expect(saveButtons.length).toBe(3)
    await act(async () => {
      saveButtons[1].dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 60))
    })
    expect(qualityActions.updateQualityNotificationSetting).toHaveBeenCalledWith(
      'inspection_trend_alert',
      expect.objectContaining({
        is_enabled: false,
        inspection_lines: expect.arrayContaining([
          expect.objectContaining({ entity_code: 'qc_finished_internal' }),
          expect.objectContaining({ entity_code: 'qc_finished_pure_water' }),
        ]),
      }),
    )
    expect(document.body.textContent).toContain('成品检验趋势异常提醒设置已保存')
  })

  it('shows warning hint when the global switch is off', async () => {
    qualityActions.fetchQualityNotificationSettings.mockResolvedValue(
      SETTINGS.map((item) => ({ ...item, is_enabled: false })),
    )
    await renderPanel()
    expect(container.textContent).toContain('总开关已关闭，所有产品线均不会发送提醒')
  })

  it('surfaces loading failure via error alert', async () => {
    qualityActions.fetchQualityNotificationSettings.mockRejectedValue(
      new Error('通知服务不可用'),
    )
    await renderPanel()
    expect(document.body.textContent).toContain('通知设置加载失败')
    const rules = [...document.querySelectorAll<HTMLButtonElement>('[data-platform-notice] button')]
      .find((button) => button.textContent?.includes('了解访问规则'))!
    await act(async () => rules.click())
    expect(document.body.textContent).toContain('通知服务不可用')
  })

  it('shows error message when saving change action plan settings fails', async () => {
    qualityActions.updateQualityNotificationSetting.mockRejectedValue(
      new Error('飞书配置未启用'),
    )
    await renderPanel()
    const saveButton = Array.from(container.querySelectorAll('button')).find(
      (btn) => /保\s*存/.test(btn.textContent || ''),
    )
    await act(async () => {
      saveButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 60))
    })
    expect(document.body.textContent).toContain('保存失败：飞书配置未启用')
  })

  it('toggles a single inspection line switch and persists the change', async () => {
    await renderPanel()
    const switches = Array.from(container.querySelectorAll('button.ant-switch'))
    // 开关顺序：变更计划卡、检验卡总开关、手动重分析发送、霉酚酸（内控）、纯化水
    expect(switches.length).toBeGreaterThanOrEqual(5)
    await act(async () => {
      switches[3].dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    qualityActions.updateQualityNotificationSetting.mockResolvedValue({
      ...SETTINGS[1],
    })
    const saveButtons = Array.from(container.querySelectorAll('button')).filter(
      (btn) => /保\s*存/.test(btn.textContent || ''),
    )
    await act(async () => {
      saveButtons[1].dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 60))
    })
    expect(qualityActions.updateQualityNotificationSetting).toHaveBeenCalledWith(
      'inspection_trend_alert',
      expect.objectContaining({
        inspection_lines: expect.arrayContaining([
          expect.objectContaining({
            entity_code: 'qc_finished_internal',
            enabled: false,
          }),
          expect.objectContaining({
            entity_code: 'qc_finished_pure_water',
            enabled: true,
          }),
        ]),
      }),
    )
  })

  it('shows error message when saving inspection trend settings fails', async () => {
    await renderPanel()
    qualityActions.updateQualityNotificationSetting.mockRejectedValue(
      new Error('网络中断'),
    )
    const saveButtons = Array.from(container.querySelectorAll('button')).filter(
      (btn) => /保\s*存/.test(btn.textContent || ''),
    )
    expect(saveButtons.length).toBe(3)
    await act(async () => {
      saveButtons[1].dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 60))
    })
    expect(document.body.textContent).toContain('保存失败：网络中断')
  })

  it('preloads QA person options into recipient selects', async () => {
    apiClient.fetchQaPersonOptions.mockResolvedValue([
      { name: '张三', open_id: 'ou_qa_1' },
    ])
    await renderPanel()
    expect(apiClient.fetchQaPersonOptions).toHaveBeenCalled()
  })

  async function searchRecipient(name: string, index = 0) {
    const input = container.querySelectorAll<HTMLInputElement>('.ant-select input')[index]
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, name)
      input.dispatchEvent(new Event('input', { bubbles: true }))
      input.dispatchEvent(new Event('change', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 350))
    })
  }

  it.each([
    ['兜底接收人', 0],
    ['第一条产品线接收人', 1],
    ['第一条产品线QA', 2],
    ['第二条产品线接收人', 3],
    ['第二条产品线QA', 4],
    ['首推接收人', 5],
  ])('%s supports typing a name to search the HR directory', async (_, index) => {
    apiClient.searchQualityPersonOptions.mockResolvedValue([{ open_id: 'ou_search', name: '搜索人员' }])
    await renderPanel()
    await searchRecipient('搜索', Number(index))
    expect(apiClient.searchQualityPersonOptions).toHaveBeenCalledWith('搜索')
    expect(document.body.querySelector('.ant-select-dropdown')?.textContent).toContain('搜索人员')
  })

  it('filters unrelated QA preload candidates while searching', async () => {
    apiClient.fetchQaPersonOptions.mockResolvedValue([{ open_id: 'ou_qa', name: '王五' }])
    apiClient.searchQualityPersonOptions.mockResolvedValue([{ open_id: 'ou_hr', name: '张三' }])
    await renderPanel()
    await searchRecipient('张', 2)
    const popup = document.body.querySelector('.ant-select-dropdown')
    expect(popup?.textContent).toContain('张三')
    expect(popup?.textContent).not.toContain('王五')
  })

  it('explains when no active user matches the searched name', async () => {
    await renderPanel()
    await searchRecipient('查无此人', 1)
    expect(document.body.querySelector('.ant-select-dropdown')?.textContent).toContain('未找到匹配的在职人员')
    expect(container.textContent).toContain('陈连平')
  })

  it('searches recipients in the HR-backed directory and displays their names', async () => {
    apiClient.searchQualityPersonOptions.mockResolvedValue([{ open_id: 'ou_hr', name: '张三' }])
    await renderPanel()
    await searchRecipient('张')
    expect(apiClient.searchQualityPersonOptions).toHaveBeenCalledWith('张')
    expect(apiClient.searchChangeActionPlanPersons).not.toHaveBeenCalled()
    expect(document.body.textContent).toContain('张三')
  })

  it('reports search failures while retaining configured recipients', async () => {
    apiClient.searchQualityPersonOptions.mockRejectedValue(new Error('无权限查询人员'))
    await renderPanel()
    await searchRecipient('张')
    expect(document.body.textContent).toContain('人员搜索失败：无权限查询人员')
    expect(container.textContent).toContain('兜底人')
  })

  it('ignores an old search response after the keyword is cleared', async () => {
    let finishSearch!: (people: { open_id: string; name: string }[]) => void
    apiClient.searchQualityPersonOptions.mockReturnValue(new Promise((resolve) => {
      finishSearch = resolve
    }))
    await renderPanel()
    await searchRecipient('张')
    await searchRecipient('')
    await act(async () => finishSearch([{ open_id: 'ou_old', name: '过期搜索结果' }]))
    expect(document.body.textContent).not.toContain('过期搜索结果')
    expect(container.textContent).toContain('兜底人')
  })

  it('reports QA preload errors instead of treating them as empty candidates', async () => {
    apiClient.fetchQaPersonOptions.mockRejectedValue(new Error('联系人尚未同步'))
    await renderPanel()
    expect(document.body.textContent).toContain('QA 人员加载失败：联系人尚未同步')
  })

  it('saves the trend alert card and reports success', async () => {
    await renderPanel()
    const saveButtons = Array.from(container.querySelectorAll('button')).filter(
      (btn) => /保\s*存/.test(btn.textContent || ''),
    )
    await act(async () => {
      saveButtons[1].dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 60))
    })
    expect(qualityActions.updateQualityNotificationSetting).toHaveBeenCalled()
  })

  it('warns when the escalation card has no first recipients', async () => {
    await renderPanel()
    const saveButtons = Array.from(container.querySelectorAll('button')).filter(
      (btn) => /保\s*存/.test(btn.textContent || ''),
    )
    await act(async () => {
      saveButtons[2].dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 60))
    })
    expect(document.body.textContent).toContain('请至少选择一位首推接收人')
  })
})
