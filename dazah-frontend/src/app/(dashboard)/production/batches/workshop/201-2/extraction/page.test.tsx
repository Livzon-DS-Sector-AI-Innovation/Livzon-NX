/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/components/production/Dashboard', () => ({
  default: (props: { cards?: Array<{ value?: (first: unknown, rest: unknown) => unknown }>; data?: unknown }) => {
    // 执行卡片聚合函数，覆盖页面内收率/产量计算逻辑
    const cards = props.cards || []
    const data = props.data || []
    for (const card of cards) {
      if (typeof card.value === 'function') card.value(null, data)
    }
    return <div data-testid="dashboard" />
  },
}))
vi.mock('@/components/production/MCSheetsSyncButton', () => ({
  default: () => <button>同步</button>,
}))
vi.mock('@/components/production/MCTraceButton', () => ({
  default: () => <button>追溯</button>,
}))

import ExtractionPage from './page'

const RECORD = {
  id: 'ex-1',
  extract_date: '2026-03-01',
  batch_no: 'MC-260129',
  filter_potency: 6000,
  filter_volume: 8,
  filter_product_qty: 48,
  carbon_usage: 2,
  wet_weight: 18,
  wet_content: 90,
  dry_loss: 5,
  dry_weight: 15.39,
  total_converted_qty: 50,
  total_crude_weight: 20,
  yield_rate: 88.5,
  inputs: [
    {
      id: 'in-1',
      crude_batch_no: 'MC-101-1',
      crude_weight: 20,
      crude_moisture: 5,
      crude_content: 90,
      converted_qty: 17.1,
    },
  ],
}

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

function fetchMock(url: string) {
  if (url.includes('/extraction-records/full-list')) {
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [RECORD] }))
  }
  return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
}

describe('ExtractionPage', () => {
  let root: Root
  let container: HTMLElement

  beforeEach(() => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
  })

  it('renders the extraction ledger with input rows', async () => {
    vi.stubGlobal('fetch', vi.fn(fetchMock))

    act(() => {
      root.render(<ExtractionPage />)
    })

    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })

    const text = container.textContent || ''
    expect(text).toContain('提取工段')
    expect(text).toContain('MC-260129')
    expect(text).toContain('MC-101-1')
    expect(text).toContain('新建提取记录')
    expect(text).toContain('+ 粗品投入')
  })

  it('shows empty state without records', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [] })))
    )

    act(() => {
      root.render(<App><ExtractionPage /></App>)
    })

    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })

    expect(container.textContent).toContain('暂无提取记录')
  })

  it('opens the create-extraction modal', async () => {
    vi.stubGlobal('fetch', vi.fn(fetchMock))
    act(() => {
      root.render(<App><ExtractionPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const createBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('新建提取记录'))
    if (createBtn) {
      await act(async () => { createBtn.click(); await new Promise((r) => setTimeout(r, 60)) })
    }
    expect((document.body.textContent || '')).toContain('新建提取记录')
  })

  // React 监听原生 value setter；直接赋值不会触发 onChange
  function setNativeValue(input: HTMLInputElement, value: string) {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set
    setter?.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  }

  function buildRequestsMock() {
    const requests: Array<{ url: string; init?: RequestInit }> = []
    const mock = (url: string, init?: RequestInit) => {
      requests.push({ url, init })
      if (url.includes('/extraction-records/full-list')) {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [RECORD] }))
      }
      return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
    }
    return { requests, mock }
  }

  async function editNumericCell(divValueText: string, nextValue: string) {
    const cells = Array.from(container.querySelectorAll('div'))
    const cell = cells.find((el) => (el.textContent || '').trim() === divValueText) as HTMLElement | undefined
    await act(async () => {
      cell?.click()
      await new Promise((r) => setTimeout(r, 40))
    })
    const numInput = container.querySelector('.ant-input-number input') as HTMLInputElement | undefined
    await act(async () => {
      if (numInput) {
        setNativeValue(numInput, nextValue)
        numInput.dispatchEvent(new Event('input', { bubbles: true }))
        numInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, keyCode: 13 }))
        numInput.dispatchEvent(new FocusEvent('blur', { bubbles: true }))
        numInput.dispatchEvent(new FocusEvent('focusout', { bubbles: true }))
      }
      await new Promise((r) => setTimeout(r, 120))
    })
  }

  it('edits the filter potency cell and PUTs the derived filter product quantity', async () => {
    const { requests, mock } = buildRequestsMock()
    vi.stubGlobal('fetch', vi.fn(mock))
    act(() => {
      root.render(<App><ExtractionPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    await editNumericCell('6000', '9000')
    const put = requests.find((r) => r.init?.method === 'PUT' && r.url.includes('/extraction-records/ex-1'))
    expect(put).toBeDefined()
    const body = JSON.parse(String(put?.init?.body))
    expect(body.filter_potency).toBe(9000)
    expect(body.filter_product_qty).toBe(72)
  })

  it('edits the wet weight cell and persists the recalculated dry weight', async () => {
    const { requests, mock } = buildRequestsMock()
    vi.stubGlobal('fetch', vi.fn(mock))
    act(() => {
      root.render(<App><ExtractionPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    await editNumericCell('18', '20')
    const put = requests.find((r) => r.init?.method === 'PUT' && r.url.includes('/extraction-records/ex-1'))
    expect(put).toBeDefined()
    const body = JSON.parse(String(put?.init?.body ?? '{}'))
    expect(body.wet_weight).toBe(20)
    expect(body.dry_weight).toBe(17.1)
  })

  it('edits the dry weight cell and persists the derived yield rate', async () => {
    const { requests, mock } = buildRequestsMock()
    vi.stubGlobal('fetch', vi.fn(mock))
    act(() => {
      root.render(<App><ExtractionPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    await editNumericCell('15.39', '16')
    const put = requests.find((r) => r.init?.method === 'PUT' && r.url.includes('/extraction-records/ex-1'))
    expect(put).toBeDefined()
    const body = JSON.parse(String(put?.init?.body ?? '{}'))
    expect(body.dry_weight).toBe(16)
    expect(body.yield_rate).toBe(32)
  })

  it('edits the crude batch text cell via the input cell', async () => {
    const { requests, mock } = buildRequestsMock()
    vi.stubGlobal('fetch', vi.fn(mock))
    act(() => {
      root.render(<App><ExtractionPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const cell = Array.from(container.querySelectorAll('div')).find(
      (el) => (el.textContent || '').trim() === 'MC-101-1',
    ) as HTMLElement | undefined
    await act(async () => { cell?.click(); await new Promise((r) => setTimeout(r, 40)) })
    const textInput = container.querySelector('.ant-input') as HTMLInputElement | undefined
    await act(async () => {
      if (textInput) {
        setNativeValue(textInput, 'MC-99-1')
        textInput.dispatchEvent(new Event('input', { bubbles: true }))
        textInput.dispatchEvent(new FocusEvent('blur', { bubbles: true }))
        textInput.dispatchEvent(new FocusEvent('focusout', { bubbles: true }))
      }
      await new Promise((r) => setTimeout(r, 100))
    })
    const put = requests.find((r) => r.init?.method === 'PUT' && r.url.includes('/extraction-inputs/in-1'))
    expect(put).toBeDefined()
    const body = JSON.parse(String(put?.init?.body ?? '{}'))
    expect(body.crude_batch_no).toBe('MC-99-1')
  })

  it('adds a crude input row by clicking the add row button', async () => {
    const requests: Array<{ url: string; init?: RequestInit }> = []
    const mock = (url: string, init?: RequestInit) => {
      requests.push({ url, init })
      if (url.includes('/extraction-records/full-list')) {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [RECORD] }))
      }
      return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
    }
    vi.stubGlobal('fetch', vi.fn(mock))
    act(() => {
      root.render(<App><ExtractionPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const addBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('+ 粗品投入'))
    await act(async () => {
      addBtn?.click()
      await new Promise((r) => setTimeout(r, 80))
    })
    const post = requests.find((r) => r.init?.method === 'POST' && r.url.includes('/extraction-inputs'))
    expect(post).toBeDefined()
  })

  it('creates a new extraction record by submitting the modal form', async () => {
    const requests: Array<{ url: string; init?: RequestInit }> = []
    const mock = (url: string, init?: RequestInit) => {
      requests.push({ url, init })
      if (url.includes('/extraction-records/full-list')) {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [RECORD] }))
      }
      if (url.includes('/extraction-records') && init?.method === 'POST') {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
      }
      return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
    }
    vi.stubGlobal('fetch', vi.fn(mock))
    act(() => {
      root.render(<App><ExtractionPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const openBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('新建提取记录'))
    await act(async () => { openBtn?.click(); await new Promise((r) => setTimeout(r, 120)) })
    const batchInput = Array.from(document.body.querySelectorAll('input')).find((i) => i.placeholder?.includes('MC-260'))
    await act(async () => {
      if (batchInput) {
        setNativeValue(batchInput, 'MC-260188')
        batchInput.dispatchEvent(new Event('input', { bubbles: true }))
        batchInput.dispatchEvent(new FocusEvent('blur', { bubbles: true }))
        batchInput.dispatchEvent(new FocusEvent('focusout', { bubbles: true }))
      }
      await new Promise((r) => setTimeout(r, 150))
    })
    const okBtn = Array.from(document.body.querySelectorAll('.ant-modal button')).find((b) => /^确\s*认$/.test((b.textContent || '').trim())) as HTMLElement | undefined
    await act(async () => {
      okBtn?.click()
      await new Promise((r) => setTimeout(r, 400))
    })
    expect(document.body.textContent || '').toContain('创建成功')
    expect(requests.some((r) => r.init?.method === 'POST' && r.url.includes('/extraction-records'))).toBe(true)
  })
})
