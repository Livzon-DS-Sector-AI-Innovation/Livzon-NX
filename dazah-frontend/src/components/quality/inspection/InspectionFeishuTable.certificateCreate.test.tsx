/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))

const mocks = vi.hoisted(() => ({
  fetchInspectionFeishuFields: vi.fn(),
  fetchInspectionFeishuRecordDetail: vi.fn(),
  deleteInspectionFeishuRecord: vi.fn(),
  pullInspectionFeishuRecords: vi.fn(),
}))

vi.mock('@/lib/api/client/quality', () => ({
  fetchInspectionFeishuFields: mocks.fetchInspectionFeishuFields,
  fetchInspectionFeishuRecordDetail: mocks.fetchInspectionFeishuRecordDetail,
}))

vi.mock('@/actions/quality-inspection', () => ({
  deleteInspectionFeishuRecord: mocks.deleteInspectionFeishuRecord,
  pullInspectionFeishuRecords: mocks.pullInspectionFeishuRecords,
  createInspectionFeishuRecord: vi.fn(),
  updateInspectionFeishuRecord: vi.fn(),
  analyzeInstrumentCertificate: vi.fn(),
}))

import { InspectionFeishuTable } from './InspectionFeishuTable'

const LIST = {
  data: [],
  meta: { total: 0, page: 1, page_size: 20, configured: true, fields: [] },
}

let container: HTMLDivElement
let root: Root

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  vi.stubGlobal(
    'fetch',
    vi.fn(async () =>
      new Response(JSON.stringify(LIST), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    ),
  )
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
  document.body.replaceChildren()
  vi.unstubAllGlobals()
  vi.clearAllMocks()
})

async function renderTable(props: Record<string, unknown>) {
  mocks.fetchInspectionFeishuFields.mockResolvedValue({
    fields: [{ field_name: '器具名称', ui_type: 'Text', editable: true }],
    can_push: true,
    form_url: null,
  })
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  act(() => {
    root.render(
      <QueryClientProvider client={queryClient}>
        <App>
          {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
          <InspectionFeishuTable {...(props as any)} />
        </App>
      </QueryClientProvider>,
    )
  })
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 60))
  })
}

function findButton(text: string) {
  return Array.from(document.querySelectorAll('button')).find(
    (node) => node.textContent === text,
  )
}

const BASE_PROPS = {
  title: '外部校准、检定',
  listApi: '/api/v1/quality/instruments/cal-external',
  entityCode: 'qc_instr_cal_external',
  editable: true,
}

describe('InspectionFeishuTable 证书识别新增入口', () => {
  it('enableCertificateCreate 时显示「证书识别新增」并打开上传弹窗', async () => {
    await renderTable({ ...BASE_PROPS, enableCertificateCreate: true })
    const button = findButton('证书识别新增')
    expect(button).toBeTruthy()
    expect(findButton('新增')).toBeTruthy()

    await act(async () => {
      button!.click()
      await new Promise((resolve) => setTimeout(resolve, 20))
    })
    expect(document.body.textContent).toContain('上传校准证书识别新增')
    expect(document.body.textContent).toContain('开始识别')
  })

  it('未开启时不显示证书识别入口', async () => {
    await renderTable({ ...BASE_PROPS })
    expect(findButton('证书识别新增')).toBeUndefined()
  })
})

describe('InspectionFeishuTable 刷新按钮', () => {
  it('点击刷新重新加载列表数据', async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    mocks.fetchInspectionFeishuFields.mockResolvedValue({
      fields: [],
      can_push: true,
      form_url: null,
    })
    act(() => {
      root.render(
        <QueryClientProvider client={queryClient}>
          <App>
            {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
            <InspectionFeishuTable {...({ ...BASE_PROPS } as any)} />
          </App>
        </QueryClientProvider>,
      )
    })
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 60))
    })

    const button = Array.from(document.querySelectorAll('button')).find(
      (node) => node.textContent === '刷新',
    )
    expect(button).toBeTruthy()
    await act(async () => {
      button!.click()
      await new Promise((resolve) => setTimeout(resolve, 20))
    })
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ['quality-inspection', 'list', BASE_PROPS.listApi],
    })
  })
})
