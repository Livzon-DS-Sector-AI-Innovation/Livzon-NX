import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getWorkPermitDetail: vi.fn(),
}))

vi.mock('@/actions/safety', () => ({
  getWorkPermitDetail: mocks.getWorkPermitDetail,
}))

vi.mock('next/navigation', () => ({
  notFound: () => {
    throw new Error('not-found')
  },
}))

const detailProps = vi.hoisted(() => ({ last: vi.fn() }))

vi.mock('@/components/safety', () => ({
  WorkPermitDetailView: (props: Record<string, unknown>) => {
    detailProps.last(props)
    return null
  },
}))

import DetailPage from './page'

const DETAIL = { id: 'p1', permit_no: 'DH-1' }

describe('作业票详情页装配', () => {
  it('加载成功时把详情传给详情视图', async () => {
    mocks.getWorkPermitDetail.mockResolvedValue({ code: 200, data: DETAIL })
    await DetailPage({ params: Promise.resolve({ id: 'p1' }) } as never).then(
      (element) => renderToStaticMarkup(element),
    )
    expect(mocks.getWorkPermitDetail).toHaveBeenCalledWith(
      'p1',
      'safety:ops-safety:work-permits',
    )
    expect(detailProps.last).toHaveBeenCalledWith({ initialDetail: DETAIL })
  })

  it('详情不存在时 404', async () => {
    mocks.getWorkPermitDetail.mockResolvedValue({ code: 404, data: null })
    await expect(
      DetailPage({ params: Promise.resolve({ id: 'x' }) } as never).then(
        (element) => renderToStaticMarkup(element),
      ),
    ).rejects.toThrow('not-found')
  })
})
