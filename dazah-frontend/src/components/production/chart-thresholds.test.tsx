/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useChartThresholds } from './chart-thresholds'

// 警戒线配置 hook：从后端读取映射 + PUT 保存后更新本地值。

const fetchMock = vi.fn()

function Harness({ scopeKey, onReady }: { scopeKey?: string; onReady: (v: Record<string, number>, save: (k: string, t: number) => Promise<boolean>) => void }) {
  const { values, save } = useChartThresholds(scopeKey)
  return (
    <div>
      <span data-testid="yield">{String(values['yield'] ?? '')}</span>
      <button
        data-testid="save"
        onClick={() => { void save('yield', 90).then(() => onReady(values, save)) }}
      >
        save
      </button>
    </div>
  )
}

describe('useChartThresholds', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('从后端读取范围配置映射', async () => {
    fetchMock.mockResolvedValueOnce({
      json: async () => ({ code: 200, data: { yield: 95 } }),
    })
    act(() => {
      root.render(<Harness scopeKey="workshop-201-2/crude-extraction" onReady={() => {}} />)
    })
    await act(async () => { await new Promise((r) => setTimeout(r, 30)) })
    expect(container.querySelector('[data-testid="yield"]')?.textContent).toBe('95')
    expect(fetchMock.mock.calls[0][0]).toContain('scope_key=workshop-201-2%2Fcrude-extraction')
  })

  it('保存走 PUT 并更新本地值', async () => {
    fetchMock
      .mockResolvedValueOnce({ json: async () => ({ code: 200, data: {} }) })
      .mockResolvedValueOnce({ json: async () => ({ code: 200, data: { scope_key: 's', chart_key: 'yield', threshold: 90 } }) })
    let saved = false
    act(() => {
      root.render(<Harness scopeKey="workshop-201-2/crude-extraction" onReady={() => { saved = true }} />)
    })
    await act(async () => { await new Promise((r) => setTimeout(r, 30)) })
    const btn = container.querySelector('[data-testid="save"]') as HTMLButtonElement
    await act(async () => { btn.click(); await new Promise((r) => setTimeout(r, 30)) })
    expect(saved).toBe(true)
    const putCall = fetchMock.mock.calls.find((c) => c[1]?.method === 'PUT')
    expect(putCall).toBeTruthy()
    expect(JSON.parse(putCall![1].body)).toEqual({
      scope_key: 'workshop-201-2/crude-extraction',
      chart_key: 'yield',
      threshold: 90,
    })
    expect(container.querySelector('[data-testid="yield"]')?.textContent).toBe('90')
  })

  it('scopeKey 缺省时不发请求', async () => {
    act(() => {
      root.render(<Harness onReady={() => {}} />)
    })
    await act(async () => { await new Promise((r) => setTimeout(r, 20)) })
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
