/* @vitest-environment happy-dom */
import { App } from 'antd'
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, it, vi } from 'vitest'
import HazardIdentificationDetail from './HazardIdentificationDetail'

const mocks = vi.hoisted(() => ({
  router: { push: vi.fn() },
  load: vi.fn(),
}))

vi.mock('next/navigation', () => ({
  useParams: () => ({ id: 'record-1' }),
  useRouter: () => mocks.router,
}))
vi.mock('@/actions/safety', () => ({ getHazardIdentification: mocks.load }))
vi.mock('@/hooks/usePagePermissions', () => ({
  usePagePermissions: () => ({ canOperate: true, canApprove: true, canReject: false }),
}))

it.each([true, false])('renders ledger and workflow actions separately (ledger=%s)', async (ledger) => {
  mocks.load.mockResolvedValue({
    code: 200,
    data: {
      id: 'record-1',
      hazard_id_no: 'HI-TEST',
      overall_status: 'in_progress',
      ai_node_progress: 'pending_script1',
      script1_review_status: 'pending',
      hazard_source: '测试记录',
    },
  })
  const container = document.createElement('div')
  document.body.append(container)
  const root = createRoot(container)
  try {
    await act(async () => root.render(
      <App><HazardIdentificationDetail ledger={ledger} /></App>,
    ))
    expect(container.textContent).toContain('HI-TEST')
    const buttons = [...container.querySelectorAll('button')]
    expect(buttons.some((button) => button.textContent === '执行AI')).toBe(!ledger)
    const back = buttons.find((button) => button.textContent === '返回列表')
    expect(back).toBeDefined()
    await act(async () => back?.click())
    expect(mocks.router.push).toHaveBeenLastCalledWith(
      ledger ? '/safety/hazard-identification/ledger' : '/safety/hazard-identification',
    )
  } finally {
    act(() => root.unmount())
    container.remove()
  }
})
