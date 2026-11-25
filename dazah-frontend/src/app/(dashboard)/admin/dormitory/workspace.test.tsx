/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, describe, expect, it, vi } from 'vitest'

const mirrorProps = vi.hoisted(() => [] as Array<Record<string, unknown>>)
const dashboardProps = vi.hoisted(() => [] as Array<Record<string, unknown>>)

vi.mock('@/components/feishu-data', () => ({
  MappedDatasetPage: (props: Record<string, unknown>) => {
    mirrorProps.push(props)
    return <div data-testid="mirror" />
  },
}))
vi.mock('@/components/administration/DormitoryDashboard', () => ({
  default: (props: Record<string, unknown>) => {
    dashboardProps.push(props)
    return (
      <button type="button" data-testid="checkin-done" onClick={props.onCheckinSuccess as () => void}>
        done
      </button>
    )
  },
}))

import DormitoryWorkspace from './workspace'

let root: Root | null = null

function render(node: React.ReactNode) {
  const container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  act(() => {
    root!.render(node)
  })
  return container
}

afterEach(() => {
  act(() => root?.unmount())
  root = null
  document.body.innerHTML = ''
  mirrorProps.length = 0
  dashboardProps.length = 0
})

describe('DormitoryWorkspace', () => {
  it('renders the dashboard above the mirror with dormitory default sort', () => {
    render(<DormitoryWorkspace />)
    expect(dashboardProps).toHaveLength(1)
    expect(dashboardProps[0].onCheckinSuccess).toBeTypeOf('function')
    expect(mirrorProps).toHaveLength(1)
    expect(mirrorProps[0]).toMatchObject({
      moduleCode: 'administration',
      pageKey: 'admin:dormitory',
      title: '宿舍管理',
      enableAdvancedQuery: true,
      enableExport: true,
      // 员工住宿退宿清单页签默认按房间编号升序（表格无日期字段，平台不自动排序）
      defaultSort: { tabName: '员工住宿退宿清单', fieldName: '房间编号', direction: 'asc' },
    })
    // 住宿表联系方式是手机号不是邮箱，人员头像按 email 关联无命中，不开启
    expect(mirrorProps[0].enablePersonAvatars).toBeFalsy()
  })

  it('remounts the mirror after a successful checkin', async () => {
    const container = render(<DormitoryWorkspace />)
    const trigger = container.querySelector('[data-testid="checkin-done"]')
    expect(trigger).toBeTruthy()
    await act(async () => {
      ;(trigger as HTMLButtonElement).click()
      await Promise.resolve()
    })
    expect(mirrorProps.length).toBeGreaterThanOrEqual(2)
  })
})
