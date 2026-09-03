/* @vitest-environment happy-dom */
import { act, createElement, Fragment } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { renderFeishuValue } from './renderFeishuValue'

type MsgApi = Parameters<typeof renderFeishuValue>[3]

function makeMessage(): MsgApi {
  return {
    error: vi.fn(),
    success: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
    loading: vi.fn(),
    open: vi.fn(),
    destroy: vi.fn(),
  } as unknown as MsgApi
}

let container: HTMLDivElement
let root: Root

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

function renderValue(node: unknown) {
  act(() => root.render(createElement(Fragment, null, node as never)))
}

describe('renderFeishuValue', () => {
  it('renders empty markers as dash', () => {
    renderValue(renderFeishuValue([], {}, 'entity', makeMessage()))
    expect(container.textContent).toBe('-')
    renderValue(renderFeishuValue(null, {}, 'entity', makeMessage()))
    expect(container.textContent).toBe('-')
    renderValue(renderFeishuValue('', {}, 'entity', makeMessage()))
    expect(container.textContent).toBe('-')
  })

  it('renders attachment list as clickable buttons downloading via proxy', async () => {
    const blob = new Blob(['x'], { type: 'image/png' })
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, blob: async () => blob })
    vi.stubGlobal('fetch', fetchMock)
    const createObjectURL = vi.fn(() => 'blob:proxy')
    const revokeObjectURL = vi.fn()
    Object.defineProperty(URL, 'createObjectURL', { value: createObjectURL, configurable: true })
    Object.defineProperty(URL, 'revokeObjectURL', { value: revokeObjectURL, configurable: true })
    const openMock = vi.fn()
    vi.stubGlobal('open', openMock)

    const msg = makeMessage()
    renderValue(
      renderFeishuValue(
        [{ name: '检验报告.pdf', file_token: 'ft-1', url: 'blob:direct' }],
        { record_id: 'rec-1' },
        'finish_inspect',
        msg as never,
      ),
    )
    const button = container.querySelector('button')
    expect(button?.textContent).toBe('检验报告.pdf')
    await act(async () => {
      button?.click()
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/quality/inspection/feishu/finish_inspect/records/rec-1/attachments/ft-1/content',
    )
    expect(openMock).toHaveBeenCalledWith('blob:proxy', '_blank')
  })

  it('attachment download failure surfaces backend message via toast', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 403,
        json: async () => ({ message: '附件未授权给当前应用' }),
      }),
    )
    const msg = makeMessage()
    renderValue(
      renderFeishuValue(
        [{ name: 'a.pdf', file_token: 'ft-2', url: 'blob:x' }],
        { record_id: 'r2' },
        'ent',
        msg as never,
      ),
    )
    await act(async () => {
      container.querySelector('button')?.click()
    })
    expect(msg.error).toHaveBeenCalledWith('附件未授权给当前应用')
  })

  it('attachment without token falls back to direct url open', async () => {
    const openMock = vi.fn()
    vi.stubGlobal('open', openMock)
    renderValue(
      renderFeishuValue(
        [{ name: 'link.pdf', url: 'https://files.example/a.pdf' }],
        {},
        undefined,
        makeMessage() as never,
      ),
    )
    await act(async () => {
      container.querySelector('button')?.click()
    })
    expect(openMock).toHaveBeenCalledWith(
      'https://files.example/a.pdf',
      '_blank',
      'noopener,noreferrer',
    )
  })

  it('renders person arrays with avatar initials and names', () => {
    renderValue(
      renderFeishuValue(
        [
          { name: '张三', avatar_url: '' },
          { name: '李四' },
        ],
        {},
        'ent',
        makeMessage() as never,
      ),
    )
    expect(container.textContent).toContain('张三')
    expect(container.textContent).toContain('李四')
  })

  it('joins plain scalar arrays with 、', () => {
    renderValue(renderFeishuValue(['A', 'B', 'C'], {}, 'ent', makeMessage() as never))
    expect(container.textContent).toBe('A、B、C')
  })

  it('renders object person by name and link objects as anchors', () => {
    renderValue(renderFeishuValue({ name: '王五' }, {}, 'ent', makeMessage() as never))
    expect(container.textContent).toContain('王五')

    renderValue(
      renderFeishuValue(
        { link: 'https://a.test', text: '公告' },
        {},
        'ent',
        makeMessage() as never,
      ),
    )
    const anchor = container.querySelector('a')
    expect(anchor?.getAttribute('href')).toBe('https://a.test')
    expect(anchor?.textContent).toBe('公告')
  })

  it('stringifies remaining scalar values', () => {
    renderValue(renderFeishuValue(42, {}, 'ent', makeMessage() as never))
    expect(container.textContent).toBe('42')
  })

  it('renders image attachments inline via proxy builder (no download button)', async () => {
    const blob = new Blob(['x'], { type: 'image/jpeg' })
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, blob: async () => blob })
    vi.stubGlobal('fetch', fetchMock)
    const createObjectURL = vi.fn(() => 'blob:proxy')
    Object.defineProperty(URL, 'createObjectURL', { value: createObjectURL, configurable: true })
    const openMock = vi.fn()
    vi.stubGlobal('open', openMock)

    const msg = makeMessage()
    renderValue(
      renderFeishuValue(
        [{ name: '封面.jpeg', file_token: 'ft-qc-1' }],
        { record_id: 'rec-qc-1' },
        undefined,
        msg as never,
        {
          attachmentUrlBuilder: (entityCode, recordId, fileToken) =>
            `/api/v1/quality/validation-qc/records/${recordId}/attachments/${fileToken}/content?year=2026&entity=${entityCode ?? ''}`,
        },
      ),
    )
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/quality/validation-qc/records/rec-qc-1/attachments/ft-qc-1/content?year=2026&entity=',
    )
    expect(createObjectURL).toHaveBeenCalled()
    // 图片内联展示，没有下载按钮、不触发 window.open
    expect(container.querySelector('button')).toBeNull()
    expect(openMock).not.toHaveBeenCalled()
  })

  it('formats DateTime ms values and Checkbox booleans by uiType', () => {
    renderValue(
      renderFeishuValue(
        new Date(2026, 2, 26, 0, 0, 0).getTime(),
        {},
        undefined,
        makeMessage() as never,
        { uiType: 'DateTime' },
      ),
    )
    expect(container.textContent).toBe('2026-03-26')

    renderValue(
      renderFeishuValue('True', {}, undefined, makeMessage() as never, { uiType: 'Checkbox' }),
    )
    expect(container.textContent).toBe('是')

    renderValue(
      renderFeishuValue('False', {}, undefined, makeMessage() as never, { uiType: 'Checkbox' }),
    )
    expect(container.textContent).toBe('否')
  })

  it('formats string ms timestamps to date for DateTime fields', () => {
    // 飞书 DateTime 可能返回字符串毫秒时间戳，须转成日期而非显示原始时间戳。
    // 使用 UTC 正午的时间戳，避免格式化结果随测试环境时区漂移（本地东八区 vs CI UTC）。
    renderValue(
      renderFeishuValue('1769774400000', {}, undefined, makeMessage() as never, {
        uiType: 'DateTime',
      }),
    )
    expect(container.textContent).toBe('2026-01-30')
  })

  it('renders image attachment with direct url when no file_token', async () => {
    const openMock = vi.fn()
    vi.stubGlobal('open', openMock)
    renderValue(
      renderFeishuValue(
        [{ name: 'cover.png', url: 'https://files.example/cover.png' }],
        { record_id: 'rec-1' },
        undefined,
        makeMessage() as never,
      ),
    )
    // 无 file_token 但有 url 时直接内联展示图片，不触发 window.open
    const img = container.querySelector('img')
    expect(img?.getAttribute('src')).toBe('https://files.example/cover.png')
    expect(openMock).not.toHaveBeenCalled()
  })

  it('falls back to download button when image blob fetch fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: false, status: 403, json: async () => ({ message: '无权限' }) }),
    )
    const msg = makeMessage()
    renderValue(
      renderFeishuValue(
        [{ name: 'fail.jpeg', file_token: 'ft-9' }],
        { record_id: 'rec-9' },
        'ent',
        msg as never,
        {
          attachmentUrlBuilder: (e, r, f) => `/api/v1/quality/validation-qc/records/${r}/attachments/${f}/content`,
        },
      ),
    )
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 30))
    })
    // 失败后回退为可点击下载按钮
    const button = Array.from(container.querySelectorAll('button')).find(
      (b) => (b.textContent || '').includes('fail.jpeg'),
    )
    expect(button).toBeTruthy()
  })
})
