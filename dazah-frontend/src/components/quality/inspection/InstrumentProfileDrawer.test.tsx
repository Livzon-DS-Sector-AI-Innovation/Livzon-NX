/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const clientMocks = vi.hoisted(() => ({
  fetchInstrumentProfile: vi.fn(),
}))

vi.mock('@/lib/api/client/quality', () => clientMocks)

import { InstrumentProfileDrawer } from './InstrumentProfileDrawer'

const PROFILE = {
  equipment: {
    record_id: 'r1',
    '设备编号': 'EQUIP-01',
    '设备名称': '压片机',
    '入厂日期': '2024-05-01',
    '安装地点': '固体车间',
  },
  matched_code: 'EQUIP-01',
  maintenance: [{ '维护日期': '2026-02-01', '维护内容': '润滑' }],
  repairs: [{ '维修日期': '2026-03-01', '维修内容': '更换轴承' }],
  calibration: {
    internal_summary: [{ '校准日期': '2026-01-10', '校准结果': '合格' }],
    internal_plan: [],
    external: [],
  },
  contracts: [],
  contracts_total: 0,
}

let container: HTMLDivElement
let root: Root

function renderDrawer(record: unknown = { '设备名称': '压片机', record_id: 'r1' }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  act(() => {
    root.render(
      <QueryClientProvider client={queryClient}>
        <App>
          <InstrumentProfileDrawer
            open
            record={record as never}
            onClose={vi.fn()}
          />
        </App>
      </QueryClientProvider>,
    )
  })
}

async function flush(ms = 60) {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, ms))
  })
}

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  clientMocks.fetchInstrumentProfile.mockResolvedValue(PROFILE)
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
  document.body
    .querySelectorAll('.ant-drawer, .ant-message')
    .forEach((node) => node.remove())
  vi.clearAllMocks()
})

describe('InstrumentProfileDrawer', () => {
  it('renders equipment fields and calibration/maintenance tabs', async () => {
    renderDrawer()
    await flush(200)
    expect(clientMocks.fetchInstrumentProfile).toHaveBeenCalledWith('r1')
    const text = document.body.textContent || ''
    expect(text).toContain('仪器档案：压片机')
    expect(text).toContain('EQUIP-01')
    expect(text).toContain('固体车间')
    expect(text).toContain('校验情况')
    expect(text).toContain('维护保养')
    expect(text).toContain('维修记录')
  })

  it('shows a loading spinner while the profile is fetching', async () => {
    clientMocks.fetchInstrumentProfile.mockReturnValue(
      new Promise(() => {}),
    )
    renderDrawer()
    await flush(30)
    expect(document.body.querySelector('.ant-spin')).not.toBeNull()
  })

  it('shows an alert when the profile query fails', async () => {
    clientMocks.fetchInstrumentProfile.mockRejectedValue(
      new Error('飞书读取失败'),
    )
    renderDrawer()
    await flush()
    expect(document.body.textContent).toContain('飞书读取失败')
  })
})