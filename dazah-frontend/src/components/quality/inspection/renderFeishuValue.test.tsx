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
})
