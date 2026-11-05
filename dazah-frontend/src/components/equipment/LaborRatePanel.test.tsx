/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App as AntApp } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  fetchLaborRatesClient: vi.fn(),
  fetchAllUsersClient: vi.fn(),
  fetchRoles: vi.fn(),
  saveLaborRate: vi.fn(),
  deleteLaborRate: vi.fn(),
  updateLaborRate: vi.fn(),
}))

vi.mock('@/lib/api/equipment-client', () => ({
  fetchLaborRatesClient: api.fetchLaborRatesClient,
  fetchAllUsersClient: api.fetchAllUsersClient,
}))
vi.mock('@/lib/api/equipment-personnel', () => ({
  fetchRoles: api.fetchRoles,
}))
vi.mock('@/actions/equipment', () => ({
  saveLaborRate: api.saveLaborRate,
  deleteLaborRate: api.deleteLaborRate,
  updateLaborRate: api.updateLaborRate,
}))

import { LaborRatePanel } from './LaborRatePanel'

const rates = [
  {
    id: 'rate-1',
    scope: 'person' as const,
    role_id: null,
    person_id: 'u-1',
    hourly_rate: 80,
    effective_from: '2026-11-01',
    remark: '高级维修工',
  },
  {
    id: 'rate-2',
    scope: 'role' as const,
    role_id: 'role-1',
    person_id: null,
    hourly_rate: 50,
    effective_from: '2026-11-01',
    remark: null,
  },
]

describe('LaborRatePanel', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    api.fetchLaborRatesClient.mockResolvedValue(rates)
    api.fetchAllUsersClient.mockResolvedValue([
      { user_id: 'u-1', name: '张三', employee_no: 'E001', department_id: 'd1' },
    ])
    api.fetchRoles.mockResolvedValue([
      { id: 'role-1', name: '维修工', code: 'MW', description: null, scope: 'equipment', is_active: true, created_at: '', updated_at: '' },
    ])
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    vi.clearAllMocks()
  })

  it('renders rates with resolved target names and priority hint', async () => {
    act(() => {
      root.render(
        <AntApp>
          <LaborRatePanel />
        </AntApp>,
      )
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    const text = document.body.textContent || ''
    expect(text).toContain('人员级（优先）')
    expect(text).toContain('张三（E001）')
    expect(text).toContain('岗位级')
    expect(text).toContain('维修工')
    expect(text).toContain('¥80.00')
    expect(text).toContain('¥50.00')
  })

  it('opens create modal with prefilled form and target selector', async () => {
    act(() => {
      root.render(
        <AntApp>
          <LaborRatePanel />
        </AntApp>,
      )
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })

    const addBtn = [...document.querySelectorAll('button')].find((b) =>
      b.textContent?.includes('新增费率'),
    ) as HTMLButtonElement
    await act(async () => {
      addBtn.click()
      await new Promise((r) => setTimeout(r, 40))
    })
    const modalText = document.body.textContent || ''
    expect(modalText).toContain('新增费率')
    expect(modalText).toContain('费率范围')
    expect(modalText).toContain('人员级（优先）')
    // 目标选择器与时薪输入已渲染
    expect(modalText).toContain('人员')
    expect(modalText).toContain('时薪（元/小时）')
    expect(modalText).toContain('生效日期')
    // 未选人直接保存：触发校验分支，动作不被调用、弹窗保持
    const okBtn = [...document.querySelectorAll('button')].find(
      (b) => b.textContent === '确 定' || b.textContent === 'OK',
    ) as HTMLButtonElement
    expect(okBtn).toBeTruthy()
    await act(async () => {
      okBtn.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((r) => setTimeout(r, 60))
    })
    expect(api.saveLaborRate).not.toHaveBeenCalled()
  })

  it('列表渲染费率金额与生效日期', async () => {
    act(() => {
      root.render(
        <AntApp>
          <LaborRatePanel />
        </AntApp>,
      )
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 80))
    })
    const text = document.body.textContent || ''
    expect(text).toContain('¥80.00')
    expect(text).toContain('¥50.00')
    expect(text).toContain('2026-11-01')
    expect(text).toContain('高级维修工')
  })
})
