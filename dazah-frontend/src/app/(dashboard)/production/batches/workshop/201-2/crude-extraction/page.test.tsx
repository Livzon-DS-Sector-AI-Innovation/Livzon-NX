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

import CrudeExtractionPage from './page'

const FULL_LIST_ITEM = {
  fermentation: { batch_no: 'MC-101-25202' },
  refining: {
    id: 'rb-1',
    batch_no: 'MC-251224',
    produce_date: '2026-03-01',
    workshop: '201-2',
    month: 3,
  },
  sub_tanks: [
    {
      sub_tank: {
        id: 'st-1',
        batch_no: 'MC-251224-1',
        fl_volume: 10,
        fl_potency: 5000,
        fl_product_qty: 50,
        total_input: 100,
        cumulative_qty: 100,
        crude_weight: 20,
        bag_weight: 10,
        crude_content: 90,
        crude_moisture: 5,
        crude_product_qty: 17.1,
        yield_rate: 92,
        cumulative_crude_qty: 20,
        cumulative_crude_yield: 92,
        remarks: '',
      },
      sodium_steps: [
        {
          id: 'na-1',
          na_before_volume: 10,
          na_after_volume: 9,
          na_potency: 6000,
          na_product_qty: 54,
          sodium_total: 54,
          ph_value: 7,
          alkali_usage: 1,
        },
      ],
      acid_steps: [
        {
          id: 'ac-1',
          acid_filter_volume: 8,
          acid_potency: 6000,
          acid_product_qty: 48,
          filter_subtotal: 48,
          ph_value: 6,
          acid_usage: 1,
          acid_filter_content: 90,
          filter_total: 48,
          na_to_fermentation_yield: 90,
          monthly_cumulative_yield: 90,
        },
      ],
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
  if (url.includes('/crude-extract/full-list')) {
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [FULL_LIST_ITEM] }))
  }
  if (url.includes('/crude-extract/fermentation-liquids')) {
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [{ batch_no: 'MC-101-25202' }] }))
  }
  return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
}

describe('CrudeExtractionPage', () => {
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

  it('renders the ledger table with nested sub-tank rows', async () => {
    vi.stubGlobal('fetch', vi.fn(fetchMock))

    act(() => {
      root.render(<CrudeExtractionPage />)
    })

    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })

    const text = container.textContent || ''
    // 导航与标题
    expect(text).toContain('粗提工段')
    expect(text).toContain('返回车间')
    // 批次与分罐数据渲染
    expect(text).toContain('MC-251224')
    expect(text).toContain('MC-101-25202')
    expect(text).toContain('MC-251224-1')
    // 新增按钮
    expect(text).toContain('新建发酵液')
    expect(text).toContain('新建提炼批次')
  })

  it('opens the create fermentation-liquid and refining-batch modals', async () => {
    vi.stubGlobal('fetch', vi.fn(fetchMock))
    act(() => {
      root.render(<App><CrudeExtractionPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const flBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('新建发酵液'))
    if (flBtn) {
      await act(async () => { flBtn.click(); await new Promise((r) => setTimeout(r, 60)) })
    }
    expect((document.body.textContent || '')).toContain('新建发酵液')
    const rbBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('新建提炼批次'))
    if (rbBtn) {
      await act(async () => { rbBtn.click(); await new Promise((r) => setTimeout(r, 60)) })
    }
    expect((document.body.textContent || '')).toContain('新建提炼批次')
  })

  it('shows empty state when no batches exist', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string) =>
        url.includes('/crude-extract/full-list')
          ? Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [] }))
          : Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [] }))
      )
    )

    act(() => {
      root.render(<CrudeExtractionPage />)
    })

    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })

    expect(container.textContent).toContain('暂无分罐数据')
  })

  // React 监听原生 value setter；直接赋值不会触发 onChange
  function setNativeValue(input: HTMLInputElement, value: string) {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set
    setter?.call(input, value)
    input.dispatchEvent(new Event('input', { bubbles: true }))
  }

  async function editNumericCell(divValueText: string, nextValue: string) {
    const cell = Array.from(container.querySelectorAll('div')).find((el) => (el.textContent || '').trim() === divValueText) as HTMLElement | undefined
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
      await new Promise((r) => setTimeout(r, 150))
    })
  }

  function crudeRequestsMock() {
    const requests: Array<{ url: string; init?: RequestInit }> = []
    const mock = (url: string, init?: RequestInit) => {
      requests.push({ url, init })
      if (url.includes('/crude-extract/full-list')) {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [FULL_LIST_ITEM] }))
      }
      if (url.includes('/crude-extract/fermentation-liquids')) {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [{ batch_no: 'MC-101-25202' }] }))
      }
      return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
    }
    return { requests, mock }
  }

  it('edits the acid filter volume cell and PUTs the derived acid product quantity', async () => {
    const { requests, mock } = crudeRequestsMock()
    vi.stubGlobal('fetch', vi.fn(mock))
    act(() => {
      root.render(<App><CrudeExtractionPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    await editNumericCell('8', '10')
    const put = requests.find((r) => r.init?.method === 'PUT' && r.url.includes('/crude-extract/acid-steps/ac-1'))
    expect(put).toBeDefined()
    const body = JSON.parse(String(put?.init?.body))
    expect(body.acid_filter_volume).toBe(10)
    expect(body.acid_product_qty).toBe(60)
  })

  it('edits the crude content cell and PUTs the derived crude product quantity', async () => {
    const { requests, mock } = crudeRequestsMock()
    vi.stubGlobal('fetch', vi.fn(mock))
    act(() => {
      root.render(<App><CrudeExtractionPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    await editNumericCell('20', '25')
    const put = requests.find((r) => r.init?.method === 'PUT' && r.url.includes('/crude-extract/sub-tank-records/st-1'))
    expect(put).toBeDefined()
    const body = JSON.parse(String(put?.init?.body))
    expect(body.crude_weight).toBe(25)
    expect(body.crude_product_qty).toBe(21.375)
  })

  it('adds a step row by clicking the add-step button', async () => {
    const requests: Array<{ url: string; init?: RequestInit }> = []
    const mock = (url: string, init?: RequestInit) => {
      requests.push({ url, init })
      if (url.includes('/crude-extract/full-list')) {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [FULL_LIST_ITEM] }))
      }
      if (url.includes('/crude-extract/fermentation-liquids')) {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [{ batch_no: 'MC-101-25202' }] }))
      }
      return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
    }
    vi.stubGlobal('fetch', vi.fn(mock))
    act(() => {
      root.render(<App><CrudeExtractionPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const addBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('+ 步骤'))
    await act(async () => { addBtn?.click(); await new Promise((r) => setTimeout(r, 120)) })
    expect(requests.some((r) => r.init?.method === 'POST' && r.url.includes('/crude-extract/sodium-steps'))).toBe(true)
    expect(requests.some((r) => r.init?.method === 'POST' && r.url.includes('/crude-extract/acid-steps'))).toBe(true)
  })

  it('warns when the create-refining-batch modal form is incomplete', async () => {
    const { mock } = crudeRequestsMock()
    vi.stubGlobal('fetch', vi.fn(mock))
    act(() => {
      root.render(<App><CrudeExtractionPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const openBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('新建提炼批次'))
    await act(async () => { openBtn?.click(); await new Promise((r) => setTimeout(r, 60)) })
    const okBtn = Array.from(document.body.querySelectorAll('.ant-modal button')).find((b) => /^确\s*认$/.test((b.textContent || '').trim())) as HTMLElement | undefined
    await act(async () => { okBtn?.click(); await new Promise((r) => setTimeout(r, 150)) })
    expect(document.body.textContent || '').toContain('请检查表单')
  })

  it('warns when the create-fermentation-liquid modal form is incomplete', async () => {
    const { mock } = crudeRequestsMock()
    vi.stubGlobal('fetch', vi.fn(mock))
    act(() => {
      root.render(<App><CrudeExtractionPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const openBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('新建发酵液'))
    await act(async () => { openBtn?.click(); await new Promise((r) => setTimeout(r, 60)) })
    const okBtn = Array.from(document.body.querySelectorAll('.ant-modal button')).find((b) => /^确\s*认$/.test((b.textContent || '').trim())) as HTMLElement | undefined
    await act(async () => { okBtn?.click(); await new Promise((r) => setTimeout(r, 150)) })
    expect(document.body.textContent || '').toContain('请检查表单')
  })

  it('clears a numeric cell value and saves null on blur', async () => {
    const requests: Array<{ url: string; init?: RequestInit }> = []
    const mock = (url: string, init?: RequestInit) => {
      requests.push({ url, init })
      if (url.includes('/crude-extract/full-list')) {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [FULL_LIST_ITEM] }))
      }
      if (url.includes('/crude-extract/fermentation-liquids')) {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [{ batch_no: 'MC-101-25202' }] }))
      }
      return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
    }
    vi.stubGlobal('fetch', vi.fn(mock))
    act(() => {
      root.render(<App><CrudeExtractionPage /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60))
    })
    const cell = Array.from(container.querySelectorAll('div')).find((el) => (el.textContent || '').trim() === '92') as HTMLElement | undefined
    await act(async () => { cell?.click(); await new Promise((r) => setTimeout(r, 40)) })
    const numInput = container.querySelector('.ant-input-number input') as HTMLInputElement | undefined
    await act(async () => {
      if (numInput) {
        setNativeValue(numInput, '')
        numInput.dispatchEvent(new Event('input', { bubbles: true }))
        numInput.dispatchEvent(new FocusEvent('blur', { bubbles: true }))
        numInput.dispatchEvent(new FocusEvent('focusout', { bubbles: true }))
      }
      await new Promise((r) => setTimeout(r, 120))
    })
    const put = requests.find((r) => r.init?.method === 'PUT' && r.url.includes('/crude-extract/sub-tank-records/st-1'))
    expect(put).toBeDefined()
    const body = JSON.parse(String(put?.init?.body))
    expect(body.yield_rate).toBeNull()
  })
})
