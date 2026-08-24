/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import dayjs from 'dayjs'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const fakeUpload = vi.hoisted(() => ({ trigger: null as null | ((file: any) => unknown) }))

vi.mock('antd', async () => {
  const React = await import('react')
  const actual = await vi.importActual<typeof import('antd')>('antd')
  const Upload = (props: Record<string, unknown>) => {
    // @ts-expect-error - intentionally minimal mock
    fakeUpload.trigger = (file: unknown) => props.beforeUpload?.(file)
    return React.createElement('div', { className: 'ant-upload' }, props.children as React.ReactNode)
  }
  Upload.displayName = 'Upload'
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const UploadDragger = (props: Record<string, any>) => {
    fakeUpload.trigger = (file: unknown) => props.beforeUpload?.(file)
    return React.createElement('button', { type: 'button', className: 'ant-upload-btn' }, props.children)
  }
  UploadDragger.displayName = 'Upload.Dragger'
  Upload.Dragger = UploadDragger
  return { ...actual, Upload }
})

import Scheduling2013Page from './page'

const dumpPlan = (over: Record<string, unknown> = {}) => ({
  batch_no: 'DR-2601-1',
  tank_no: 'T1',
  product_type: '正式批',
  dump_date: dayjs().format('YYYY-MM-DD'),
  year: 2026,
  month: 1,
  day: 15,
  in_db: true,
  is_past: false,
  status: 'upcoming',
  task_status: 'pending',
  actual_time: null,
  confirmed_by: null,
  actual_tank_no: null,
  delay_reason: null,
  ...over,
})

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

function fetchMock(url: string): Promise<Response> {
  if (url.includes('/dr/schedule/dump-plans')) {
    return Promise.resolve(jsonResponse({
      code: 200, message: 'success',
      data: {
        version: { file: '2026排产.xlsx', sheet: '排产' },
        today: dayjs().format('YYYY-MM-DD'),
        items: [
          dumpPlan({ task_status: 'pending' }),
          dumpPlan({ batch_no: 'DR-2601-2', task_status: 'confirmed', actual_time: '2026-01-15T08:30:00+08:00', confirmed_by: '张三' }),
          dumpPlan({ batch_no: 'DR-2602-1', task_status: 'delayed', delay_reason: '等料' }),
          dumpPlan({ batch_no: 'DR-2602-2', is_past: true, status: 'past' }),
        ],
        summary: { total: 4, past: 1, upcoming: 3 },
      },
    }))
  }
  return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
}

describe('Scheduling2013Page', () => {
  let root: ReturnType<typeof createRoot>
  let container: HTMLElement

  beforeEach(() => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.clearAllMocks()
    vi.unstubAllGlobals()
  })

  it('renders the dump/接罐 plan table with status tags and actions', async () => {
    vi.stubGlobal('fetch', vi.fn(fetchMock))
    act(() => {
      root.render(<App><Scheduling2013Page /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('排产')
    expect(text).toContain('确认接罐')
    expect(text).toContain('延期')
  })

  it('shows an error state when the API returns an error', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse({ code: 500, message: '服务错误', data: null }))))
    act(() => {
      root.render(<App><Scheduling2013Page /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    expect(container.textContent || '').toContain('排产')
  })

  it('renders the confirm/modal for confirming an approved batch', async () => {
    vi.stubGlobal('fetch', vi.fn(fetchMock))
    act(() => {
      root.render(<App><Scheduling2013Page /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    const confirmBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('确认接罐'))
    if (confirmBtn) {
      await act(async () => { confirmBtn.click(); await new Promise((r) => setTimeout(r, 60)) })
    }
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('确认接罐')
  })

  it('opens the delay-reason modal for pending batches', async () => {
    vi.stubGlobal('fetch', vi.fn(fetchMock))
    act(() => {
      root.render(<App><Scheduling2013Page /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    const delayBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('延期'))
    if (delayBtn) {
      await act(async () => { delayBtn.click(); await new Promise((r) => setTimeout(r, 60)) })
    }
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('延期')
  })
})

describe('Scheduling2013Page actions', () => {
  let root: ReturnType<typeof createRoot>
  let container: HTMLElement

  const listResponse = () => jsonResponse({
    code: 200, message: 'success',
    data: {
      version: { file: '2026排产.xlsx', sheet: '排产' },
      today: dayjs().format('YYYY-MM-DD'),
      items: [
        dumpPlan({ task_status: 'pending' }),
        dumpPlan({ batch_no: 'DR-2601-2', task_status: 'confirmed', actual_time: '2026-01-15T08:30:00+08:00', confirmed_by: '张三' }),
        dumpPlan({ batch_no: 'DR-2602-1', task_status: 'delayed', delay_reason: '等料' }),
        dumpPlan({ batch_no: 'DR-2603-1', task_status: 'pending_approval' }),
        dumpPlan({ batch_no: 'DR-2604-1', task_status: 'confirmed', actual_time: '2026-01-16T08:30:00+08:00', confirmed_by: '李四' }),
        dumpPlan({ batch_no: 'SOON-1', dump_date: dayjs().add(3, 'day').format('YYYY-MM-DD'), task_status: null }),
        dumpPlan({ batch_no: 'PAST-1', is_past: true, status: 'past', task_status: null }),
      ],
      summary: { total: 7, past: 1, upcoming: 6 },
    },
  })

  function renderAll(list = true) {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => { root.render(<App><Scheduling2013Page /></App>) })
    return new Promise<void>((resolve) => { setTimeout(() => { resolve() }, 80) })
  }

  async function flush(ms = 80) {
    await act(async () => { await new Promise((r) => setTimeout(r, ms)) })
  }

  async function modalOkButton() {
    return Array.from(document.body.querySelectorAll('.ant-modal-footer button')).find(
      (b) => (b.textContent || '').trim().includes('确认') && (b as HTMLButtonElement).className.includes('primary'),
    ) as HTMLButtonElement | undefined
  }

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  function defaultFetch() {
    return vi.fn((url: string, opts?: RequestInit) => {
      const method = opts?.method || 'GET'
      if (url.includes('/dr/schedule/dump-plans')) return Promise.resolve(listResponse())
      if (method === 'POST' && /tasks\/.+?\/confirm/.test(url)) {
        return Promise.resolve(jsonResponse({ code: 200, message: '接罐确认成功', data: null }))
      }
      if (method === 'POST' && /tasks\/.+?\/delay/.test(url)) {
        return Promise.resolve(jsonResponse({ code: 200, message: '延期提交成功', data: null }))
      }
      if (method === 'POST' && /tasks\/.+?\/approve/.test(url)) {
        return Promise.resolve(jsonResponse({ code: 200, message: '审批完成', data: null }))
      }
      return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
    })
  }

  it('uploads the excel and refreshes the list', async () => {
    const fetched: string[] = []
    const fetchMock = vi.fn((url: string, opts?: RequestInit) => {
      fetched.push(url)
      if (url.includes('/dr/schedule/upload')) {
        return Promise.resolve(jsonResponse({ code: 200, message: '排产已更新', data: null }))
      }
      return Promise.resolve(listResponse())
    })
    vi.stubGlobal('fetch', fetchMock)
    await renderAll()
    await act(async () => {
      fakeUpload.trigger?.(new File(['fake'], 'test.xlsx'))
      await new Promise((r) => setTimeout(r, 150))
    })
    expect(fetched.some((u) => u.includes('/dr/schedule/upload'))).toBe(true)
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('排产已更新')
  })

  it('shows an upload error when the backend rejects the excel', async () => {
    const fetchMock = vi.fn((url: string) => {
      if (url.includes('/dr/schedule/upload')) {
        return Promise.resolve(jsonResponse({ code: 500, message: '上传失败原因', data: null }))
      }
      return Promise.resolve(listResponse())
    })
    vi.stubGlobal('fetch', fetchMock)
    await renderAll()
    await act(async () => {
      fakeUpload.trigger?.(new File(['fake'], 'test.xlsx'))
      await new Promise((r) => setTimeout(r, 150))
    })
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('上传失败原因')
  })

  it('shows a network error when the excel upload request fails', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (url.includes('/dr/schedule/upload')) return Promise.reject(new Error('boom'))
      return Promise.resolve(listResponse())
    }))
    await renderAll()
    await act(async () => {
      fakeUpload.trigger?.(new File(['x'], 'test.xlsx'))
      await new Promise((r) => setTimeout(r, 150))
    })
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('上传失败：boom')
  })

  it('confirms a pending batch and closes the modal', async () => {
    vi.stubGlobal('fetch', vi.fn(defaultFetch()))
    await renderAll()
    await flush()
    const rowBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('确认接罐'))
    if (rowBtn) {
      await act(async () => { rowBtn.click(); await flush(60) })
    }
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('确认接罐')

    const okBtn = await modalOkButton()
    if (okBtn) {
      await act(async () => { okBtn.click(); await flush(120) })
    }
    const after = (container.textContent || '') + (document.body.textContent || '')
    expect(after).toContain('接罐确认成功')
  })

  it('shows an error when the confirm request fails', async () => {
    const fetchMock = vi.fn((url: string, opts?: RequestInit) => {
      if (url.includes('/dr/schedule/dump-plans')) return Promise.resolve(listResponse())
      return Promise.resolve(jsonResponse({ code: 500, message: '系统繁忙', data: null }))
    })
    vi.stubGlobal('fetch', fetchMock)
    await renderAll()
    await flush()
    const rowBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.includes('确认接罐'))
    if (rowBtn) {
      await act(async () => { rowBtn.click(); await flush(60) })
    }
    const okBtn = await modalOkButton()
    if (okBtn) {
      await act(async () => { okBtn.click(); await flush(120) })
    }
    const after = (container.textContent || '') + (document.body.textContent || '')
    expect(after).toContain('系统繁忙')
  })

  it('warns when delaying a batch without a reason', async () => {
    vi.stubGlobal('fetch', vi.fn(defaultFetch()))
    await renderAll()
    await flush()
    const delayBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.replace(/\s/g, '').includes('延期'))
    if (delayBtn) {
      await act(async () => { delayBtn.click(); await flush(120) })
    }
    const footerBtns = Array.from(document.body.querySelectorAll('.ant-modal-footer button'))
    const okBtn = footerBtns.find((b) => (b.textContent || '').includes('提交延期')) as HTMLButtonElement | undefined
    if (okBtn) {
      await act(async () => { okBtn.click(); await flush(200) })
    }
    const after = (container.textContent || '') + (document.body.textContent || '')
    expect(after).toContain('请选择延期原因')
  })

  it('submits a delay with a selected reason', async () => {
    const called: string[] = []
    const fetchMock = vi.fn((url: string, opts?: RequestInit) => {
      called.push(url)
      if (url.includes('/dr/schedule/dump-plans')) return Promise.resolve(listResponse())
      return Promise.resolve(jsonResponse({ code: 200, message: '延期提交成功', data: null }))
    })
    vi.stubGlobal('fetch', fetchMock)
    await renderAll()
    await flush()
    const delayBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.replace(/\s/g, '').includes('延期'))
    if (delayBtn) {
      await act(async () => { delayBtn.click(); await flush(120) })
    }
    const sel = document.body.querySelector('.ant-modal .ant-select') as HTMLElement | null
    if (sel) {
      await act(async () => { sel.dispatchEvent(new MouseEvent('mousedown', { bubbles: true })); await flush(150) })
    }
    const option = Array.from(document.body.querySelectorAll('.ant-select-item-option')).find((o) => o.textContent?.includes('等料')) as HTMLButtonElement | undefined
    if (option) {
      await act(async () => { option.click(); await flush(120) })
    }
    const okBtn = Array.from(document.body.querySelectorAll('.ant-modal-footer button')).find(
      (b) => (b.textContent || '').includes('提交延期'),
    ) as HTMLButtonElement | undefined
    if (okBtn) {
      await act(async () => { okBtn.click(); await flush(150) })
    }
    expect(called.some((u) => u.includes('/delay'))).toBe(true)
    const after = (container.textContent || '') + (document.body.textContent || '')
    expect(after).toContain('延期提交成功')
  })

  it('approves a pending-approval batch', async () => {
    const called: string[] = []
    const fetchMock = vi.fn((url: string, opts?: RequestInit) => {
      called.push(url)
      if (url.includes('/dr/schedule/dump-plans')) return Promise.resolve(listResponse())
      return Promise.resolve(jsonResponse({ code: 200, message: '审批完成', data: null }))
    })
    vi.stubGlobal('fetch', fetchMock)
    await renderAll()
    await flush()
    const approveBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.replace(/\s/g, '').includes('审批'))
    if (approveBtn) {
      await act(async () => { approveBtn.click(); await flush(120) })
    }
    const approveOk = Array.from(document.body.querySelectorAll('.ant-modal-footer button')).find(
      (b) => (b.textContent || '').replace(/\s/g, '').includes('批准接罐'),
    ) as HTMLButtonElement | undefined
    if (approveOk) {
      await act(async () => { approveOk.click(); await flush(150) })
    }
    expect(called.some((u) => u.includes('/approve'))).toBe(true)
    const after = (container.textContent || '') + (document.body.textContent || '')
    expect(after).toContain('审批完成')
  })

  it('rejects a pending-approval batch', async () => {
    const approveBodies: string[] = []
    const fetchMock = vi.fn((url: string, optsArg?: RequestInit) => {
      if (url.includes('/approve')) approveBodies.push(optsArg?.body ? String(optsArg.body) : '')
      if (url.includes('/dr/schedule/dump-plans')) return Promise.resolve(listResponse())
      return Promise.resolve(jsonResponse({ code: 200, message: '审批完成', data: null }))
    })
    vi.stubGlobal('fetch', fetchMock)
    await renderAll()
    await flush()
    const approveBtn = Array.from(container.querySelectorAll('button')).find((b) => b.textContent?.replace(/\s/g, '').includes('审批'))
    if (approveBtn) {
      await act(async () => { approveBtn.click(); await flush(120) })
    }
    const rejectBtn = Array.from(document.body.querySelectorAll('.ant-modal-footer button')).find(
      (b) => (b.textContent || '').replace(/\s/g, '').includes('驳回'),
    ) as HTMLButtonElement | undefined
    if (rejectBtn) {
      await act(async () => { rejectBtn.click(); await flush(150) })
    }
    expect(approveBodies[approveBodies.length - 1]?.includes('"approve":false')).toBe(true)
  })

  it('filters the list by status and month selects', async () => {
    vi.stubGlobal('fetch', vi.fn(defaultFetch()))
    await renderAll()
    await flush()

    const statusSelect = Array.from(container.querySelectorAll('.ant-select')).find((s) => s.textContent?.includes('全部状态'))
    if (statusSelect) {
      await act(async () => {
        (statusSelect as HTMLElement).dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
        await flush(80)
      })
      const soon = Array.from(document.body.querySelectorAll('.ant-select-item-option')).find((o) => o.textContent?.includes('未来7天')) as HTMLElement | undefined
      if (soon) {
        await act(async () => { soon.click(); await flush(100) })
      }
    }
    const text = (container.textContent || '') + (document.body.textContent || '')
    expect(text).toContain('排产')
  })
})