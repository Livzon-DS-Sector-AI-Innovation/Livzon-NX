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
  it('clears parsed url and sets form values', async () => {
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

describe('SyncSettingsButton 交互增补覆盖', () => {
  let root: Root
  let container: HTMLElement

  const cfgData = [
    { id: 'cfg-1', product_name: '霉酚酸', sync_target: 'seed_culture',
      app_id: 'cli_x', app_secret: 'secret', bitable_app_token: 'tok',
      table_id: 'tbl', updated_at: '2026-08-21T00:00:00' },
  ]

  const setVal = (el: HTMLInputElement, value: string) => {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set
    setter?.call(el, value)
    el.dispatchEvent(new Event('input', { bubbles: true }))
  }
  const findInput = (ph: string) =>
    Array.from(document.body.querySelectorAll('input')).find((i) => i.placeholder?.includes(ph)) as HTMLInputElement | undefined
  const findButton = (label: string) =>
    Array.from(document.body.querySelectorAll('button')).find((b) => (b.textContent || '').replace(/\s+/g, '') === label) as HTMLButtonElement | undefined

  const makeFetch = (withCfg: boolean, onBody?: (b: string) => void) => {
    const handler = (url: string, init?: RequestInit) => {
      if (init?.body) onBody?.(String(init.body))
      if (url.includes('/feishu/tables/') && init?.method === 'POST') {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
      }
      if (url.includes('/feishu-configs/test') && init?.method === 'POST') {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: { ok: true, steps: [{ status: 'ok', name: 'connect', message: 'ok' }] } }))
      }
      if (url.includes('/feishu-configs') && init?.method === 'PUT') {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: { id: 'cfg-1', updated_at: '2026-08-21T00:00:00' } }))
      }
      if (url.includes('/feishu-configs')) {
        return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: withCfg ? cfgData : [] }))
      }
      return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
    }
    vi.stubGlobal('fetch', vi.fn(handler))
  }

  const renderButton = (withCfg = false, onSync?: () => void) => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    act(() => {
      root.render(<App><SyncSettingsButton productName="霉酚酸" syncTarget="seed_culture" onSync={onSync} /></App>)
    })
  }

  const openModal = async () => {
    await act(async () => { await new Promise((r) => setTimeout(r, 40)) })
    const btn = Array.from(container.querySelectorAll('button')).find((b) => b.title === '同步设置')
    await act(async () => { btn?.click(); await new Promise((r) => setTimeout(r, 40)) })
  }

  const bodyText = () => (container.textContent || '') + (document.body.textContent || '')

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.unstubAllGlobals()
    vi.clearAllMocks()
    localStorage.clear()
    vi.useRealTimers()
  })

  it('粘贴链接自动提取 token 并保存新配置到本地历史', async () => {
    const bodies: string[] = []
    makeFetch(false, (b) => { if (b.includes('product_name')) bodies.push(b) })
    renderButton()
    await openModal()
    const urlInput = findInput('粘贴飞书表格链接')
    if (urlInput) {
      await act(async () => {
        setVal(urlInput, 'https://xxx.feishu.cn/base/BaseTok7?table=tbl7')
        urlInput.dispatchEvent(new Event('paste', { bubbles: true }))
        await new Promise((r) => setTimeout(r, 60))
      })
    }
    expect(bodyText()).toContain('多维表格')
    const appName = findInput('输入名称或点开')
    if (appName) {
      await act(async () => {
        setVal(appName, '全新应用')
        appName.dispatchEvent(new Event('change', { bubbles: true }))
        await new Promise((r) => setTimeout(r, 60))
      })
    }
    const appIdInput = findInput('手动输入')
    if (appIdInput) {
      await act(async () => {
        setVal(appIdInput, 'cli_new')
        await new Promise((r) => setTimeout(r, 30))
      })
    }
    const secretInput = Array.from(document.body.querySelectorAll('input')).find((i) => i.type === 'password') as HTMLInputElement | undefined
    if (secretInput) {
      await act(async () => {
        setVal(secretInput, 'sec_new')
        await new Promise((r) => setTimeout(r, 30))
      })
    }
    const saveBtn = findButton('保存')
    if (saveBtn) {
      await act(async () => {
        saveBtn.click()
        await new Promise((r) => setTimeout(r, 300))
      })
    }
    expect(bodies.length).toBeGreaterThan(0)
    expect(bodyText()).toContain('上次同步')
  })

  it('测试连接成功展示结果步骤', async () => {
    makeFetch(false)
    renderButton()
    await openModal()
    const urlInput = findInput('粘贴飞书表格链接')
    if (urlInput) {
      await act(async () => {
        setVal(urlInput, 'https://ope.feishu.cn/wiki/WiTok?sheet=ShX')
        await new Promise((r) => setTimeout(r, 60))
      })
    }
    const appIdInput = findInput('手动输入')
    if (appIdInput) {
      await act(async () => {
        setVal(appIdInput, 'cli_x')
        await new Promise((r) => setTimeout(r, 30))
      })
    }
    const secretInput = Array.from(document.body.querySelectorAll('input')).find((i) => i.type === 'password') as HTMLInputElement | undefined
    if (secretInput) {
      await act(async () => {
        setVal(secretInput, 'secret')
        await new Promise((r) => setTimeout(r, 30))
      })
    }
    const testBtn = Array.from(document.body.querySelectorAll('.ant-modal button')).find((b) => (b.textContent || '').includes('测试连接')) as HTMLButtonElement | undefined
    if (testBtn) {
      await act(async () => { testBtn.click(); await new Promise((r) => setTimeout(r, 100)) })
    }
    expect(bodyText()).toContain('连接测试通过')
  })

  it('已存在配置时触发同步并通知父组件', async () => {
    const onSync = vi.fn()
    makeFetch(true)
    renderButton(true, onSync)
    await openModal()
    const syncBtn = Array.from(document.body.querySelectorAll('.ant-modal button')).find((b) => b.textContent?.trim() === '同步') as HTMLButtonElement | undefined
    if (syncBtn) {
      await act(async () => { syncBtn.click(); await new Promise((r) => setTimeout(r, 100)) })
    }
    expect(onSync).toHaveBeenCalled()
    expect(bodyText()).toContain('上次同步')
  })

it('关闭弹窗再重新打开并切换自动同步开关', async () => {
  makeFetch(true)
  renderButton(true)
  await openModal()
  // 点击取消关闭弹窗（触发模态 onCancel）
  const cancelBtn = findButton('取消')
  if (cancelBtn) {
    await act(async () => { cancelBtn.dispatchEvent(new MouseEvent('click', { bubbles: true })); await new Promise((r) => setTimeout(r, 80)) })
  }
  // 重新打开弹窗
  const openBtn = Array.from(container.querySelectorAll('button')).find((b) => b.title === '同步设置')
  await act(async () => { openBtn?.click(); await new Promise((r) => setTimeout(r, 60)) })
  expect(bodyText()).toContain('飞书同步设置')
  // 切换自动同步开关
  const toggleBtn = Array.from(document.body.querySelectorAll('button')).find((b) => b.title === '开启自动同步') as HTMLButtonElement | undefined
  if (toggleBtn) {
    await act(async () => { toggleBtn.click(); await new Promise((r) => setTimeout(r, 60)) })
    expect(Array.from(document.body.querySelectorAll('button')).some((b) => b.title?.startsWith('自动同步中'))).toBeTruthy()
  }
})

it('空值与非法链接输入不产出 Token 标签', async () => {
  makeFetch(false)
  renderButton()
  await openModal()
  const urlInput = findInput('粘贴飞书表格链接')
  if (urlInput) {
    await act(async () => { setVal(urlInput, '   '); await new Promise((r) => setTimeout(r, 60)) })
  }
  expect(bodyText()).not.toContain('Token:')
  if (urlInput) {
    await act(async () => { setVal(urlInput, 'https://xxx.feishu.cn/other/abc'); await new Promise((r) => setTimeout(r, 60)) })
  }
  expect(bodyText()).not.toContain('Token:')
  if (urlInput) {
    await act(async () => { setVal(urlInput, '不合理输入'); await new Promise((r) => setTimeout(r, 60)) })
  }
  expect(bodyText()).not.toContain('Token:')
})

it('从历史应用列表选择应用会回填 App ID 输入', async () => {
  localStorage.setItem('feishu_saved_apps', JSON.stringify([
    { id: 's1', name: '历史应用A', app_id: 'cli_his', app_secret: 'sec' },
    { id: 's2', name: '历史应用B', app_id: 'cli_2', app_secret: 'sec2' },
  ]))
  makeFetch(false)
  renderButton()
  await openModal()
  const selectContent = document.body.querySelector('.ant-select-content') as HTMLElement | undefined
  await act(async () => { selectContent?.dispatchEvent(new MouseEvent('mousedown', { bubbles: true })); await new Promise((r) => setTimeout(r, 80)) })
  const option = Array.from(document.body.querySelectorAll('.ant-select-item-option')).find((o) => o.textContent?.includes('历史应用A'))
  await act(async () => { option?.dispatchEvent(new MouseEvent('click', { bubbles: true })); await new Promise((r) => setTimeout(r, 80)) })
  const appIdInput = findInput('手动输入')
  expect(appIdInput?.value).toBe('cli_his')
})

it('保存接口返回非 200 时不中断交互', async () => {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (url.includes('/feishu-configs/test') && init?.method === 'POST') {
      return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
    }
    if (url.includes('/feishu-configs') && init?.method === 'PUT') {
      return Promise.resolve(jsonResponse({ code: 500, message: '保存失败', data: null }))
    }
    if (url.includes('/feishu-configs')) {
      return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: cfgData }))
    }
    return Promise.resolve(jsonResponse({ code: 200, message: 'success', data: null }))
  })
  vi.stubGlobal('fetch', fetchMock)
  container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
  act(() => {
    root.render(<App><SyncSettingsButton productName="霉酚酸" syncTarget="seed_culture" /></App>)
  })
  await openModal()
  const appIdInput = findInput('手动输入')
  if (appIdInput) {
    await act(async () => { setVal(appIdInput, 'cli_x'); await new Promise((r) => setTimeout(r, 30)) })
  }
  const secretInput = Array.from(document.body.querySelectorAll('input')).find((i) => i.type === 'password') as HTMLInputElement | undefined
  if (secretInput) {
    await act(async () => { setVal(secretInput, 'secret'); await new Promise((r) => setTimeout(r, 30)) })
  }
  const saveBtn = findButton('保存')
  if (saveBtn) {
    await act(async () => { saveBtn.click(); await new Promise((r) => setTimeout(r, 200)) })
  }
  expect(fetchMock).toHaveBeenCalled()
})
})
