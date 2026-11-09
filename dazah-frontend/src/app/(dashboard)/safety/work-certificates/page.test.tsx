import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getWorkCertificates: vi.fn(),
  getCertificateExpirySummary: vi.fn(),
}))

vi.mock('@/actions/safety', () => ({
  getWorkCertificates: mocks.getWorkCertificates,
  getCertificateExpirySummary: mocks.getCertificateExpirySummary,
}))

const panelProps = vi.hoisted(() => ({ last: vi.fn() }))

vi.mock('@/components/safety', () => ({
  WorkCertificatePanel: (props: Record<string, unknown>) => {
    panelProps.last(props)
    return null
  },
}))

import WorkCertificatesPage from './page'

describe('特种作业证件页装配', () => {
  it('携带 ?cert= 深链时把证件 id 传给面板', async () => {
    mocks.getWorkCertificates.mockResolvedValue({
      code: 200,
      data: { items: [], total: 0 },
    })
    mocks.getCertificateExpirySummary.mockResolvedValue({
      code: 200,
      data: { total: 0 },
    })
    await WorkCertificatesPage({
      searchParams: Promise.resolve({ cert: 'c9' }),
    } as never).then((element) => renderToStaticMarkup(element))
    expect(mocks.getWorkCertificates).toHaveBeenCalledWith(
      expect.objectContaining({ pageKey: 'safety:ops-safety:work-certificates' }),
    )
    expect(panelProps.last).toHaveBeenCalledWith({
      initialList: { items: [], total: 0 },
      initialSummary: { total: 0 },
      initialError: null,
      highlightCertId: 'c9',
    })
  })

  it('无深链时 highlightCertId 为 null', async () => {
    mocks.getWorkCertificates.mockResolvedValue({
      code: 200,
      data: { items: [], total: 0 },
    })
    mocks.getCertificateExpirySummary.mockResolvedValue({
      code: 200,
      data: { total: 0 },
    })
    await WorkCertificatesPage({
      searchParams: Promise.resolve({}),
    } as never).then((element) => renderToStaticMarkup(element))
    expect(panelProps.last).toHaveBeenCalledWith(
      expect.objectContaining({ highlightCertId: null }),
    )
  })

  it('加载失败时传错误提示给面板', async () => {
    mocks.getWorkCertificates.mockResolvedValue({ code: 500, message: '库不可用' })
    mocks.getCertificateExpirySummary.mockResolvedValue({ code: 200, data: null })
    await WorkCertificatesPage({
      searchParams: Promise.resolve({}),
    } as never).then((element) => renderToStaticMarkup(element))
    expect(panelProps.last).toHaveBeenCalledWith(
      expect.objectContaining({ initialError: '库不可用' }),
    )
  })
})
