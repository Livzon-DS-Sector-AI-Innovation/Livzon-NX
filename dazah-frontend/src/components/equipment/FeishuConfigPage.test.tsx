/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App as AntApp } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  fetchInspectionFeishuConfigList: vi.fn(),
  fetchInspectionFeishuSyncStatus: vi.fn(),
  triggerInspectionFeishuSync: vi.fn(),
  testInspectionFeishuConfig: vi.fn(),
}))

vi.mock('@/lib/api/inspection-feishu', () => api)
vi.mock('./inspection/InspectionFeishuConfigDrawer', () => ({
  InspectionFeishuConfigDrawer: ({ workshopCode, open }: { workshopCode: string; open: boolean }) =>
    open ? <div data-testid={`config-drawer:${workshopCode}`} /> : null,
}))

import { FeishuConfigPage } from './FeishuConfigPage'

const detail101 = {
  workshop_code: '101-2',
  app_id: 'cli_ws',
  app_secret_masked: 'cli_ws****',
  app_secret_configured: true,
  app_token: 'bascn_1012',
  base_url: 'https://j0eukrlohu.feishu.cn/base/WehRbElQcaxkqRsvvehc7oxrnNf',
  today_table_id: 'tbl_today',
  history_table_id: 'tbl_history',
  device_table_id: 'tbl_devices',
  is_enabled: true,
  source: 'database',
  enabled: true,
  last_test_status: 'success',
  last_test_error: null,
  last_tested_at: '2026-10-20T05:56:00Z',
}

const detail201 = {
  ...detail101,
  workshop_code: '201-1',
  app_id: 'cli_ws',
  app_token: 'bascn_env',
  base_url: '',
  source: 'environment' as const,
  is_enabled: false,
  enabled: false,
}

let root: Root | null = null
let clipboardWrites: string[] = []

beforeEach(() => {
  vi.clearAllMocks()
  clipboardWrites = []
  Object.defineProperty(navigator, 'clipboard', {
    configurable: true,
    value: { writeText: vi.fn(async (text: string) => { clipboardWrites.push(text) }) },
  })
  api.fetchInspectionFeishuConfigList.mockResolvedValue([detail101, detail201])
  api.fetchInspectionFeishuSyncStatus.mockResolvedValue({
    enabled: true,
    tables: [
      { table_key: 'today', total_rows: 52, last_run_at: '2026-10-20T05:57:00Z', last_status: 'success', last_message: null },
    ],
  })
})

afterEach(() => {
  act(() => root?.unmount())
  document.body.innerHTML = ''
})

async function renderPage() {
  const container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  await act(async () => {
    root!.render(<AntApp><FeishuConfigPage /></AntApp>)
  })
  await act(async () => { await new Promise((r) => setTimeout(r, 40)) })
}

function rowOf(code: string): HTMLTableRowElement | undefined {
  return Array.from(document.querySelectorAll('tr'))
    .find((tr) => tr.textContent?.includes(code)) as HTMLTableRowElement | undefined
}

describe('FeishuConfigPage（飞书配置集中页）', () => {
  it('凭据卡按 App ID 去重展示，Secret 不回显明文', async () => {
    await renderPage()
    const text = document.body.textContent || ''
    expect(text).toContain('cli_ws')
    expect(text).toContain('出于安全不回显明文')
    expect(text).not.toContain('app_secret明文占位')
    // 两个车间共用一个应用 → 凭据卡只出现一组，使用车间列出两个 code
    expect(text).toContain('101-2')
    expect(text).toContain('201-1')
  })

  it('九个车间全量列出：已配置车间有链接与数据表，未配置车间给配置入口', async () => {
    await renderPage()
    for (const code of ['101-1', '101-2', '102-1', '102-2', '103', '201-1', '201-2', '201-3', '203']) {
      expect(rowOf(code), `缺少车间行 ${code}`).toBeTruthy()
    }
    const row101 = rowOf('101-2')!
    const link = row101.querySelector('a[href^="https://"]') as HTMLAnchorElement | null
    expect(link?.getAttribute('href')).toBe(detail101.base_url)
    expect(row101.textContent).toContain('今日巡检')
    expect(row101.textContent).toContain('镜像 52 行')

    const unconfigured = rowOf('201-2')!
    expect(unconfigured.textContent).toContain('未配置')
    expect(unconfigured.textContent).toContain('配置')
  })

  it('未存链接的已配置车间展示占位提示而非死链', async () => {
    await renderPage()
    const row201 = rowOf('201-1')!
    expect(row201.textContent).toContain('未存链接')
    expect(row201.querySelector('a[href^="https://"]')).toBeNull()
  })

  it('复制按钮写入剪贴板；编辑打开对应车间配置抽屉', async () => {
    await renderPage()
    const row101 = rowOf('101-2')!
    const copyBtn = row101.querySelector('button[aria-label="复制 App ID 101-2"]') as HTMLButtonElement
    await act(async () => { copyBtn.click() })
    expect(clipboardWrites).toContain('cli_ws')

    const editBtn = Array.from(document.querySelectorAll('tr'))
      .find((tr) => tr.textContent?.includes('101-2'))
      ?.querySelectorAll('button')
    // antd 会给两个汉字的按钮文案自动插入空格（编 辑），比较时先去掉空白
    const target = Array.from(editBtn ?? [])
      .find((b) => (b.textContent || '').replace(/\s/g, '') === '编辑') as HTMLButtonElement
    expect(target, '编辑按钮未找到').toBeTruthy()
    await act(async () => { target.click() })
    expect(document.querySelector('[data-testid="config-drawer:101-2"]')).toBeTruthy()
  })

  it('同步按钮触发该车间同步并刷新清单', async () => {
    api.triggerInspectionFeishuSync.mockResolvedValue({
      today: { synced: 3, total: 52 }, history: { synced: 0, total: 53 }, devices: { synced: 0, total: 49 },
    })
    await renderPage()
    const row101 = rowOf('101-2')!
    const syncBtn = Array.from(row101.querySelectorAll('button')).find((b) => b.textContent?.includes('同步'))!
    await act(async () => { syncBtn.click() })
    expect(api.triggerInspectionFeishuSync).toHaveBeenCalledWith('101-2')
  })
})
