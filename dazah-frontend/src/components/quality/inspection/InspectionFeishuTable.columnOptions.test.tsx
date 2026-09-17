/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))

const apiClient = vi.hoisted(() => ({
  fetchInspectionFeishuFields: vi.fn(),
  fetchInspectionMaterials: vi.fn(),
  fetchInspectionFeishuRecordDetail: vi.fn(),
}))

const inspectionActions = vi.hoisted(() => ({
  pullInspectionFeishuRecords: vi.fn(),
  deleteInspectionFeishuRecord: vi.fn(),
}))

vi.mock('@/lib/api/client/quality', () => apiClient)
vi.mock('@/actions/quality-inspection', () => inspectionActions)

import { InspectionFeishuTable } from './InspectionFeishuTable'

const LIST_RESPONSE = {
  data: [
    {
      record_id: 'rec-1',
      维护内容: '清洗溶剂滤头、检查管路密封',
      是否完成: '否',
      '剩余天数（提前1周通知）': 21,
    },
    {
      record_id: 'rec-2',
      维护内容: '清洗单向阀',
      是否完成: '否',
      '剩余天数（提前1周通知）': 5,
    },
    {
      record_id: 'rec-3',
      维护内容: '更换光源灯',
      是否完成: '否',
      '剩余天数（提前1周通知）': 2,
    },
    {
      record_id: 'rec-4',
      维护内容: '更换光源灯',
      是否完成: '是',
      '剩余天数（提前1周通知）': 5,
    },
  ],
  meta: {
    total: 1,
    page: 1,
    page_size: 20,
    configured: true,
    fields: ['维护内容', '是否完成', '剩余天数（提前1周通知）'],
    last_sync_time: null,
  },
}

let container: HTMLDivElement
let root: Root

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  apiClient.fetchInspectionFeishuFields.mockResolvedValue({
    fields: [
      { field_name: '维护内容', ui_type: 'Text', editable: true },
      { field_name: '是否完成', ui_type: 'SingleSelect', editable: true },
      { field_name: '剩余天数（提前1周通知）', ui_type: 'Formula', editable: false },
    ],
    can_push: false,
  })
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify(LIST_RESPONSE), { status: 200 })),
  )
})

afterEach(async () => {
  await act(async () => {
    root.unmount()
  })
  container.remove()
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

function renderTable(props: Partial<Parameters<typeof InspectionFeishuTable>[0]> = {}) {
  act(() => {
    root.render(
      <QueryClientProvider client={new QueryClient()}>
        <App>
          <InspectionFeishuTable
            title="设备维护保养记录"
            listApi="/api/v1/quality/instruments/maintenance"
            entityCode="qc_instr_maintenance"
            {...props}
          />
        </App>
      </QueryClientProvider>,
    )
  })
}

describe('InspectionFeishuTable 列显示定制', () => {
  it('columnLabels 改列头、columnWidths 缩列、valueTags 亮色标记是否完成', async () => {
    renderTable({
      columnLabels: { '剩余天数（提前1周通知）': '剩余天数' },
      columnWidths: { '剩余天数（提前1周通知）': 90, 维护内容: 220 },
      valueTags: { 是否完成: { 是: { color: 'green' }, 否: { color: 'red' } } },
    })
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 80))
    })
    const text = container.textContent || ''
    expect(text).toContain('剩余天数')
    expect(text).not.toContain('提前1周通知')
    // 是否完成=否 渲染为红色 Tag
    const tag = container.querySelector('.ant-tag-red')
    expect(tag).not.toBeNull()
    expect(tag?.textContent).toBe('否')
    expect(text).toContain('清洗溶剂滤头、检查管路密封')
  })

  it('剩余天数按行动态高亮：未完成 ≤3 红 / ≤7 橙，已完成与宽裕天数正常', async () => {
    renderTable({
      columnLabels: { '剩余天数（提前1周通知）': '剩余天数' },
      valueTags: { 是否完成: { 是: { color: 'green' }, 否: { color: 'red' } } },
      cellHighlights: {
        '剩余天数（提前1周通知）': (record) => {
          if (record['是否完成'] === '是') return null
          const days = Number(record['剩余天数（提前1周通知）'])
          if (Number.isNaN(days)) return null
          if (days <= 3) return { color: 'red' }
          if (days <= 7) return { color: 'orange' }
          return null
        },
      },
    })
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 80))
    })
    const redTags = Array.from(container.querySelectorAll('.ant-tag-red'))
    const orangeTags = Array.from(container.querySelectorAll('.ant-tag-orange'))
    // rec-3 未完成 2 天 → 红；rec-2 未完成 5 天 → 橙
    expect(redTags.map((t) => t.textContent)).toContain('2')
    expect(orangeTags.map((t) => t.textContent)).toContain('5')
    // rec-4 已完成 5 天：不标剩余天数色（其「是」走 valueTags 红色标签）
    const body = container.textContent || ''
    expect(body).toContain('21')
  })
})
