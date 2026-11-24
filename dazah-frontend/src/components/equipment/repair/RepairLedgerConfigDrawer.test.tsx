/* @vitest-environment happy-dom */

import { act, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  fetchRepairConfig: vi.fn(),
  updateRepairConfig: vi.fn(),
  testRepairConfig: vi.fn(),
  fetchFeishuApps: vi.fn(),
}))

vi.mock('@/lib/api/repair-ledger', () => ({
  fetchRepairConfig: api.fetchRepairConfig,
  updateRepairConfig: api.updateRepairConfig,
  testRepairConfig: api.testRepairConfig,
}))
vi.mock('@/lib/api/inspection-feishu', () => ({ fetchFeishuApps: api.fetchFeishuApps }))

// 保留真实的 Drawer / Form / Input；下拉与开关换成原生控件，便于在 happy-dom 里操作。
// Form.Item 仍会把 value / onChange 注入到这些子组件，校验与取值逻辑走真实表单。
vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>()
  type Option = { value?: string | number; label?: ReactNode }
  const Select = ({
    value, onChange, options, id,
  }: {
    value?: string | number
    onChange?: (value: string | number | undefined, option?: unknown) => void
    options?: Option[]
    id?: string
  }) => (
    <select
      id={id}
      value={value === undefined || value === null ? '' : String(value)}
      onChange={(event) => onChange?.(event.target.value, undefined)}
    >
      {(options ?? []).map((option) => (
        <option key={String(option.value)} value={String(option.value)}>{option.label}</option>
      ))}
    </select>
  )
  const Switch = ({
    checked, onChange, id,
  }: {
    checked?: boolean
    onChange?: (checked: boolean, event: unknown) => void
    id?: string
  }) => (
    <input
      id={id}
      type="checkbox"
      checked={Boolean(checked)}
      onChange={(event) => onChange?.(event.target.checked, event)}
    />
  )
  return { ...actual, Select, Switch }
})

import { App as AntApp } from 'antd'
import { RepairLedgerConfigDrawer } from './RepairLedgerConfigDrawer'

const config = (overrides: Record<string, unknown> = {}) => ({
  workshop_code: '201-1',
  feishu_app_id: null,
  app_name: '',
  app_id: '',
  app_secret_masked: '',
  app_secret_configured: false,
  app_token: '',
  table_id: '',
  base_url: '',
  is_enabled: false,
  enabled: false,
  last_test_status: null,
  last_test_error: null,
  last_tested_at: null,
  ...overrides,
})

const apps = [
  { id: 'app-1', name: '设备巡检应用', app_id: 'cli_app_1' },
  { id: 'app-2', name: '生产台账应用', app_id: 'cli_app_2' },
]

let container: HTMLDivElement
let root: Root
const props = { onClose: vi.fn(), onSaved: vi.fn() }

// 表单校验、字段联动与消息提示都是异步的，用宏任务逐轮推进
const flush = async (turns = 4) => {
  for (let i = 0; i < turns; i++) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
  }
}

const renderDrawer = async () => {
  await act(async () => {
    root.render(
      <AntApp>
        <RepairLedgerConfigDrawer
          workshopCode="201-1"
          workshopLabel="201一车间"
          open
          onClose={props.onClose}
          onSaved={props.onSaved}
        />
      </AntApp>,
    )
  })
  await flush()
}

// Drawer 渲染在 document.body 的 portal 里
const field = (labelText: string) =>
  Array.from(document.querySelectorAll('.ant-drawer-open .ant-form-item'))
    .find((node) => node.querySelector('label')?.textContent?.trim() === labelText) ?? null
const inputOf = (labelText: string) =>
  field(labelText)?.querySelector<HTMLInputElement>('input') ?? null
const selectOf = (labelText: string) =>
  field(labelText)?.querySelector<HTMLSelectElement>('select') ?? null

const typeInto = async (labelText: string, value: string) => {
  const input = inputOf(labelText)
  if (!input) throw new Error(`未找到输入框：${labelText}`)
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await flush(2)
}

const selectOption = async (labelText: string, value: string) => {
  const select = selectOf(labelText)
  if (!select) throw new Error(`未找到下拉框：${labelText}`)
  await act(async () => {
    select.value = value
    select.dispatchEvent(new Event('change', { bubbles: true }))
  })
  await flush(2)
}

const blur = async (labelText: string) => {
  await act(async () => {
    inputOf(labelText)?.dispatchEvent(new FocusEvent('focusout', { bubbles: true }))
  })
  await flush(2)
}

const toggle = async (labelText: string) => {
  await act(async () => {
    inputOf(labelText)?.click()
  })
  await flush(2)
}

// antd 会在两字按钮中间插入空格，比较时忽略空白
const button = (text: string) =>
  Array.from(document.querySelectorAll<HTMLButtonElement>('.ant-drawer-open button'))
    .find((node) => (node.textContent ?? '').replace(/\s+/g, '') === text) ?? null

const clickButton = async (text: string) => {
  await act(async () => {
    button(text)?.click()
  })
  await flush()
}

const drawerText = () => document.querySelector('.ant-drawer-open')?.textContent ?? ''
const validationErrors = () =>
  Array.from(document.querySelectorAll('.ant-drawer-open .ant-form-item-explain-error'))
    .map((node) => node.textContent?.trim())
    .filter(Boolean)
    .join(' | ')
/** 当前用例内出现的全部提示（上一个用例的提示在 beforeEach 里清掉） */
const notices = () =>
  Array.from(document.querySelectorAll('.ant-message-notice'))
    .map((node) => node.textContent?.trim())
    .filter((text): text is string => Boolean(text))

beforeEach(() => {
  vi.clearAllMocks()
  document.querySelectorAll('.ant-message').forEach((node) => node.remove())
  api.fetchRepairConfig.mockResolvedValue(config())
  api.fetchFeishuApps.mockResolvedValue(apps)
  api.updateRepairConfig.mockResolvedValue(config({ enabled: true }))
  api.testRepairConfig.mockResolvedValue({ success: true, message: '连接成功，数据表共 12 条记录' })
  container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
  document.querySelectorAll('.ant-message, .ant-drawer').forEach((node) => node.remove())
})

describe('RepairLedgerConfigDrawer', () => {
  it('loads the saved config and the registered apps when opened', async () => {
    api.fetchRepairConfig.mockResolvedValue(config({
      feishu_app_id: 'app-2',
      app_token: 'bascnabc',
      table_id: 'tblXYZ',
      is_enabled: true,
      enabled: true,
      last_test_status: 'failed',
      last_test_error: '飞书多维表格访问失败',
    }))
    await renderDrawer()

    expect(api.fetchRepairConfig).toHaveBeenCalledWith('201-1')
    expect(api.fetchFeishuApps).toHaveBeenCalledOnce()
    expect(inputOf('检修表链接')?.value).toBe('bascnabc')
    expect(inputOf('数据表 Table ID')?.value).toBe('tblXYZ')
    expect(selectOf('飞书自建应用')?.value).toBe('app-2')
    expect(inputOf('启用自动同步')?.checked).toBe(true)
    expect(drawerText()).toContain('同步已启用')
    expect(drawerText()).toContain('失败')
    expect(drawerText()).toContain('飞书多维表格访问失败')
    // 已登记应用与「手动输入新应用」都在下拉里
    const options = Array.from(selectOf('飞书自建应用')?.options ?? [])
      .map((option) => option.value)
    expect(options).toEqual(['app-1', 'app-2', '__manual__'])
  })

  it('recognises a pasted table link and fills the token and table id automatically', async () => {
    await renderDrawer()

    await typeInto('检修表链接', 'https://x.feishu.cn/base/bascn999?table=tblQQQ&view=vew1')
    await blur('检修表链接')
    expect(inputOf('检修表链接')?.value).toBe('bascn999')
    expect(inputOf('数据表 Table ID')?.value).toBe('tblQQQ')

    // 直接在 Table ID 栏粘贴子表链接也会被识别
    await typeInto('数据表 Table ID', 'https://x.feishu.cn/base/bascn999?table=tblWWW')
    await blur('数据表 Table ID')
    expect(inputOf('数据表 Table ID')?.value).toBe('tblWWW')

    // 知识库链接原样保留，交由后端在保存时解析
    await typeInto('检修表链接', 'https://x.feishu.cn/wiki/AbcNode?table=tblW1')
    await blur('检修表链接')
    expect(inputOf('检修表链接')?.value).toContain('/wiki/AbcNode')
    expect(inputOf('数据表 Table ID')?.value).toBe('tblW1')
    expect(notices().at(-1)).toContain('知识库链接')

    // 无法识别的网址给出提示，不改写表单
    await typeInto('检修表链接', 'https://example.com/not-feishu')
    await blur('检修表链接')
    expect(inputOf('检修表链接')?.value).toBe('https://example.com/not-feishu')
    expect(notices().at(-1)).toContain('无法识别该网址')
  })

  it('saves the config with the selected app and notifies the caller', async () => {
    // 保存后重新拉取到的是已保存的配置
    api.fetchRepairConfig
      .mockResolvedValueOnce(config())
      .mockResolvedValue(config({
        feishu_app_id: 'app-1',
        app_token: 'bascn777',
        table_id: 'tbl777',
        is_enabled: true,
        enabled: true,
      }))
    await renderDrawer()

    await selectOption('飞书自建应用', 'app-1')
    await typeInto('检修表链接', 'https://x.feishu.cn/base/bascn777?table=tbl777')
    await blur('检修表链接')
    await toggle('启用自动同步')
    expect(inputOf('启用自动同步')?.checked).toBe(true)
    await clickButton('保存配置')

    expect(api.updateRepairConfig).toHaveBeenCalledWith('201-1', {
      feishu_app_id: 'app-1',
      app_token: 'bascn777',
      table_id: 'tbl777',
      base_url: 'https://x.feishu.cn/base/bascn777?table=tbl777',
      is_enabled: true,
    })
    expect(props.onSaved).toHaveBeenCalledOnce()
    // 保存后重新拉取配置，状态行随之刷新
    expect(api.fetchRepairConfig).toHaveBeenCalledTimes(2)
    expect(drawerText()).toContain('同步已启用')
    expect(notices().at(-1)).toContain('检修表配置已保存')
  })

  it('registers a manually entered app together with its secret', async () => {
    // 首次打开是空配置；保存后重新拉取时，新应用已登记并被选中
    api.fetchRepairConfig
      .mockResolvedValueOnce(config())
      .mockResolvedValue(config({
        feishu_app_id: 'app-new',
        app_token: 'bascn000',
        table_id: 'tbl000',
        is_enabled: true,
        enabled: true,
        app_secret_configured: true,
      }))
    // 新应用保存后进入应用库，再次加载时出现在下拉里
    api.fetchFeishuApps
      .mockResolvedValueOnce(apps)
      .mockResolvedValue([...apps, { id: 'app-new', name: '设备检修应用', app_id: 'cli_new_app' }])
    await renderDrawer()

    await selectOption('飞书自建应用', '__manual__')
    await typeInto('应用名称（可选）', '设备检修应用')
    await typeInto('App ID', 'cli_new_app')
    await typeInto('App Secret', 's3cret')
    await typeInto('检修表链接', 'bascn000')
    await typeInto('数据表 Table ID', 'tbl000')
    await toggle('启用自动同步')
    await clickButton('保存配置')

    expect(api.updateRepairConfig).toHaveBeenCalledWith('201-1', {
      app_id: 'cli_new_app',
      app_secret: 's3cret',
      app_name: '设备检修应用',
      app_token: 'bascn000',
      table_id: 'tbl000',
      base_url: '',
      is_enabled: true,
    })
    expect(props.onSaved).toHaveBeenCalledOnce()
    // 保存后下拉显示新登记的应用，手输凭据区收起
    expect(selectOf('飞书自建应用')?.value).toBe('app-new')
    expect(field('App Secret')).toBeNull()
  })

  it('keeps the drawer open and shows the reason when saving fails', async () => {
    await renderDrawer()
    api.updateRepairConfig.mockRejectedValue(new Error('Table ID 以 vew 开头是视图 ID'))

    await selectOption('飞书自建应用', 'app-1')
    await typeInto('检修表链接', 'bascn111')
    await typeInto('数据表 Table ID', 'vew111')
    await toggle('启用自动同步')
    await clickButton('保存配置')

    expect(api.updateRepairConfig).toHaveBeenCalledOnce()
    expect(props.onSaved).not.toHaveBeenCalled()
    expect(document.querySelector('.ant-drawer-open')).not.toBeNull()
    expect(notices().at(-1)).toContain('视图 ID')
  })

  it('does not submit while required fields are empty', async () => {
    await renderDrawer()

    await clickButton('保存配置')

    expect(api.updateRepairConfig).not.toHaveBeenCalled()
    expect(validationErrors()).toContain('请选择已登记应用')
    expect(validationErrors()).toContain('请粘贴检修表链接')
    expect(validationErrors()).toContain('请填写数据表 Table ID')
  })

  it('tests the saved connection and reports the outcome', async () => {
    await renderDrawer()
    await clickButton('测试连接（已保存配置）')

    expect(api.testRepairConfig).toHaveBeenCalledWith('201-1')
    expect(notices().at(-1)).toContain('连接成功，数据表共 12 条记录')
    expect(api.fetchRepairConfig).toHaveBeenCalledTimes(2)

    api.testRepairConfig.mockResolvedValue({ success: false, message: '同步未启用或配置不完整' })
    await clickButton('测试连接（已保存配置）')
    expect(notices().at(-1)).toContain('同步未启用或配置不完整')

    api.testRepairConfig.mockRejectedValue(new Error('连接测试超时'))
    await clickButton('测试连接（已保存配置）')
    expect(notices().at(-1)).toContain('连接测试超时')
  })

  it('reports a failed load and closes through the footer button', async () => {
    api.fetchRepairConfig.mockRejectedValue(new Error('网络连接失败'))
    await renderDrawer()
    expect(notices().at(-1)).toContain('网络连接失败')

    await clickButton('关闭')
    expect(props.onClose).toHaveBeenCalledOnce()
  })
})
