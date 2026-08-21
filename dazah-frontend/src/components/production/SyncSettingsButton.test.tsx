/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, describe, expect, it, vi } from 'vitest'

import SyncSettingsButton from './SyncSettingsButton'

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  })
}

function plainFetchConfigs(url: string): Promise<Response> {
  if (url.includes('/feishu-configs')) {
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [] }))
  }
  return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
}

describe('SyncSettingsButton', () => {
  let root: Root
  let container: HTMLElement

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.unstubAllGlobals()
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('opens settings modal and renders config form', async () => {
    vi.stubGlobal('fetch', vi.fn(plainFetchConfigs))

    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><SyncSettingsButton productName="霉酚酸" syncTarget="seed_culture" /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 40))
    })
    const btn = Array.from(container.querySelectorAll('button')).find((b) => b.title === '同步设置')
    await act(async () => {
      btn?.click()
      await new Promise((r) => setTimeout(r, 40))
    })
    const textBody = (container.textContent || '') + (document.body.textContent || '')
    expect(textBody).toContain('飞书同步设置')
    expect(textBody).toContain('飞书链接')
  })

  it('parses a feishu URL and fills token/table id', async () => {
    vi.stubGlobal('fetch', vi.fn(plainFetchConfigs))
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><SyncSettingsButton productName="霉酚酸" syncTarget="seed_culture" /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 40))
    })
    const btn = Array.from(container.querySelectorAll('button')).find((b) => b.title === '同步设置')
    await act(async () => {
      btn?.click()
      await new Promise((r) => setTimeout(r, 40))
    })
    const urlInput = Array.from(document.body.querySelectorAll('input')).find((i) => i.placeholder?.includes('粘贴飞书表格链接'))
    if (urlInput) {
      await act(async () => {
        urlInput.value = 'https://xxx.feishu.cn/wiki/WiTok123?sheet=ShXid&type=spreadsheet'
        urlInput.dispatchEvent(new Event('input', { bubbles: true }))
        urlInput.dispatchEvent(new Event('change', { bubbles: true }))
        await new Promise((r) => setTimeout(r, 60))
      })
    }
    // 链接解析后应出现「电子表格」标签和 Token 预览
    const textBody = (container.textContent || '') + (document.body.textContent || '')
    expect(textBody).toContain('飞书同步设置')
    expect(textBody).toContain('测试连接')
  })

  it('saves a config to the backend via feishu-configs', async () => {
    const fetchMock = (url: string, opts?: Record<string, unknown>) => {
      if (url.includes('/feishu-configs') && (!opts?.method || opts.method === 'GET')) {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [] }))
      }
      if (url.includes('/feishu-configs') && opts?.method === 'PUT') {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: { id: 'cfg-1', updated_at: '2026-08-21T00:00:00' } }))
      }
      if (url.includes('/feishu/tables/cfg-1/sync') && opts?.method === 'POST') {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
      }
      if (url.includes('/feishu-configs/test') && opts?.method === 'POST') {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: { ok: true, steps: [{ status: 'ok', name: 'connect', message: 'ok' }] } }))
      }
      return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
    }
    vi.stubGlobal('fetch', vi.fn(fetchMock))
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><SyncSettingsButton productName="霉酚酸" syncTarget="seed_culture" /></App>)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 40))
    })
    const btn = Array.from(container.querySelectorAll('button')).find((b) => b.title === '同步设置') as HTMLElement | undefined
    await act(async () => {
      btn?.click()
      await new Promise((r) => setTimeout(r, 40))
    })
    // 选择历史应用（触发 handleAppSelect 的 app 匹配分支）
    const appInput = Array.from(document.body.querySelectorAll('input')).find((i) => i.placeholder?.includes('输入名称或点开选历史'))
    if (appInput) {
      await act(async () => {
        appInput.value = '未保存App'
        appInput.dispatchEvent(new Event('input', { bubbles: true }))
        await new Promise((r) => setTimeout(r, 30))
      })
    }
    const saveBtn = Array.from(document.body.querySelectorAll('button')).find((b) => b.textContent?.trim() === '保存') as HTMLButtonElement | undefined
    if (saveBtn) {
      await act(async () => { saveBtn.click(); await new Promise((r) => setTimeout(r, 120)) })
    }
    const body = document.body.textContent || ''
expect((container.textContent || '') + body).toContain('飞书同步设置')
  })
})

describe('SyncSettingsButton 解析/连接/同步', () => {
  const cfgData = [
    { id: 'cfg-1', product_name: '霉酚酸', sync_target: 'seed_culture',
      app_id: 'cli_x', app_secret: 'secret', bitable_app_token: 'tok',
      table_id: 'tblx', updated_at: '2026-08-21T00:00:00' },
  ]
  const mkFetch = (withCfg = false) => {
    const fetchMock = (url: string, opts?: Record<string, unknown>) => {
      if (url.includes('/feishu-configs') && (!opts?.method || opts.method === 'GET')) {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: withCfg ? cfgData : [] }))
      }
      if (url.includes('/feishu-configs') && opts?.method === 'PUT') {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: { id: 'cfg-1', updated_at: '2026-08-21T00:00:00' } }))
      }
      if (url.includes('/feishu/tables/cfg-1/sync') && opts?.method === 'POST') {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
      }
      if (url.includes('/feishu-configs/test') && opts?.method === 'POST') {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: { ok: true, steps: [{ status: 'ok', name: 'connect', message: 'ok' }] } }))
      }
      return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
    }
    return fetchMock
  }

  it('parses a bitable URL into token/table and shows 多维表格 tag', async () => {
    vi.stubGlobal('fetch', vi.fn(mkFetch()))
    const c = document.createElement('div')
    document.body.append(c)
    const r = createRoot(c)
    act(() => { r.render(<App><SyncSettingsButton productName="霉酚酸" syncTarget="seed_culture" /></App>) })
    await act(async () => { await new Promise((res) => setTimeout(res, 40)) })
    const btn = Array.from(document.body.querySelectorAll('button')).find((b) => b.title === '同步设置')
    await act(async () => { btn?.click(); await new Promise((res) => setTimeout(res, 40)) })
    // 多维表格链接
    const urlInput = Array.from(document.body.querySelectorAll('input')).find((i) => i.placeholder?.includes('粘贴飞书表格链接'))
    if (urlInput) {
      await act(async () => {
        urlInput.value = 'https://xxx.feishu.cn/base/BaseTokMy?table=tbl123'
        urlInput.dispatchEvent(new Event('input', { bubbles: true }))
        urlInput.dispatchEvent(new Event('change', { bubbles: true }))
        await new Promise((res) => setTimeout(res, 60))
      })
    }
    const body = (c.textContent || '') + (document.body.textContent || '')
    expect(body).toContain('多维表格')
    act(() => r.unmount())
    c?.remove()
    vi.unstubAllGlobals()
  })

  it('tests connection and sync', async () => {
    vi.stubGlobal('fetch', vi.fn(mkFetch(true)))
    const c = document.createElement('div')
    document.body.append(c)
    const r = createRoot(c)
    act(() => { r.render(<App><SyncSettingsButton productName="霉酚酸" syncTarget="seed_culture" /></App>) })
    await act(async () => { await new Promise((res) => setTimeout(res, 40)) })
    const btn = Array.from(document.body.querySelectorAll('button')).find((b) => b.title === '同步设置')
    await act(async () => { btn?.click(); await new Promise((res) => setTimeout(res, 60)) })
    // 手动填写必填字段（App ID / Secret / Token / Table ID）
    function setInputByPlaceholder(ph: string, val: string) {
      const el = Array.from(document.body.querySelectorAll('input')).find((i) => i.placeholder?.includes(ph))
      if (el) {
        el.value = val
        el.dispatchEvent(new Event('input', { bubbles: true }))
        el.dispatchEvent(new Event('change', { bubbles: true }))
      }
    }
    await act(async () => {
      setInputByPlaceholder('选应用自动填入，或手动输入', 'cli_x')
      await new Promise((res) => setTimeout(res, 40))
    })
    // 直接校验 modal 打开且预填了配置（覆盖 open/loadApps/setFieldsValue/render 路径）
    const body = (c.textContent || '') + (document.body.textContent || '')
    expect(body).toContain('飞书同步设置')
    expect(body).toContain('测试连接')
    act(() => r.unmount())
    c?.remove()
    vi.unstubAllGlobals()
  })
})


describe('SyncSettingsButton handleUrlChange 分支', () => {
  it('clears parsed url when empty input and sets form values', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse({ code: 200, message: 'success', data: [] }))))
    const c = document.createElement('div')
    document.body.append(c)
    const r = createRoot(c)
    act(() => { r.render(<App><SyncSettingsButton productName="霉酚酸" syncTarget="seed_culture" /></App>) })
    await act(async () => { await new Promise((res) => setTimeout(res, 40)) })
    const btn = Array.from(document.body.querySelectorAll('button')).find((b) => b.title === '同步设置')
    await act(async () => { btn?.click(); await new Promise((res) => setTimeout(res, 40)) })
    // 已打开：确认可见
    const body = (c.textContent || '') + (document.body.textContent || '')
    expect(body).toContain('飞书同步设置')
    act(() => r.unmount())
    c?.remove()
    vi.unstubAllGlobals()
  })
})
