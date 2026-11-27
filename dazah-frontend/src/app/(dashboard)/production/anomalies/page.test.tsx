/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const actions = vi.hoisted(() => ({
  getScheduleAnomalies: vi.fn(),
  createScheduleAnomaly: vi.fn(),
}))

vi.mock('@/actions/production', () => actions)

vi.mock('@/components/production/board-nav-blocks', () => ({
  default: () => <div data-testid="board-nav-blocks" />,
}))

const anomalyResponse = (rows: Record<string, unknown>[]) => ({
  code: 200,
  message: 'success',
  data: rows,
  meta: { page: 1, page_size: 20, total: rows.length },
})

const sampleRow = {
  id: 'a1b2c3d4',
  product_code: 'FA',
  batch_no: 'FA26314',
  tank_no: '202A',
  anomaly_type: 'reseeded',
  anomaly_type_label: '补种',
  event_date: '2026-11-28',
  reason: '移种延后，原接种作废',
  remark: null,
  created_by_name: '标记人甲',
  created_at: '2026-11-28T09:00:00+08:00',
  updated_at: '2026-11-28T09:00:00+08:00',
}

import { clearProductionAuthForTest, setProductionAdminForTest } from '@/test/production-auth'
import ProductionAnomaliesPage from './page'

let root: Root
let container: HTMLElement

async function renderPage() {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
  await act(async () => {
    root.render(
      <App>
        <ProductionAnomaliesPage />
      </App>,
    )
  })
  await act(async () => {
    await new Promise((r) => setTimeout(r, 30))
  })
}

/** React 受控输入必须走原型 setter + input 事件才能被状态层感知 */
async function setNativeValue(element: HTMLElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(
    element instanceof HTMLTextAreaElement
      ? HTMLTextAreaElement.prototype
      : HTMLInputElement.prototype,
    'value',
  )?.set
  await act(async () => {
    setter?.call(element, value)
    element.dispatchEvent(new Event('input', { bubbles: true }))
    await new Promise((r) => setTimeout(r, 30))
  })
}

function buttonByText(text: string): HTMLButtonElement | null {
  const buttons = Array.from(container.querySelectorAll('button'))
  return buttons.find((btn) => btn.textContent?.replace(/\s/g, '')?.includes(text)) ?? null
}

beforeEach(() => {
  setProductionAdminForTest()
  actions.getScheduleAnomalies.mockClear()
  actions.createScheduleAnomaly.mockClear()
  actions.getScheduleAnomalies.mockResolvedValue(anomalyResponse([sampleRow]))
  actions.createScheduleAnomaly.mockResolvedValue({
    code: 200,
    message: '异常已登记',
    data: sampleRow,
  })
})

afterEach(() => {
  clearProductionAuthForTest()
  act(() => root.unmount())
  container.remove()
  vi.restoreAllMocks()
})

describe('排产异常记录页', () => {
  it('加载后展示异常列表（类型标签、批号、标记人）', async () => {
    await renderPage()
    expect(actions.getScheduleAnomalies).toHaveBeenCalledWith(
      expect.objectContaining({ product: 'FA', page: 1, page_size: 20 }),
    )
    const text = container.textContent ?? ''
    expect(text).toContain('FA26314')
    expect(text).toContain('补种')
    expect(text).toContain('标记人甲')
    expect(text).toContain('共 1 条')
  })

  it('点击查询按筛选参数重新拉取', async () => {
    await renderPage()
    actions.getScheduleAnomalies.mockClear()
    const inputs = Array.from(container.querySelectorAll('input'))
    const batchInput = inputs.find((input) => input.placeholder === '批号')
    expect(batchInput).not.toBeNull()
    await setNativeValue(batchInput as HTMLElement, 'FA26315')
    const queryButton = buttonByText('查询')
    expect(queryButton).not.toBeNull()
    await act(async () => {
      queryButton!.click()
      await new Promise((r) => setTimeout(r, 30))
    })
    expect(actions.getScheduleAnomalies).toHaveBeenCalledWith(
      expect.objectContaining({ product: 'FA', batch_no: 'FA26315' }),
    )
  })

  it('登记异常提交成功后刷新列表', async () => {
    await renderPage()
    actions.createScheduleAnomaly.mockClear()
    const registerButton = buttonByText('登记异常')
    expect(registerButton).not.toBeNull()
    await act(async () => {
      registerButton!.click()
      await new Promise((r) => setTimeout(r, 30))
    })
    const modal = document.querySelector('.ant-modal')
    expect(modal).not.toBeNull()
    const batchInput = Array.from(modal!.querySelectorAll('input')).find(
      (input) => input.placeholder === '如 FA26314',
    )
    expect(batchInput).not.toBeNull()
    await setNativeValue(batchInput as HTMLElement, 'FA26399')
    const textAreas = Array.from(modal!.querySelectorAll('textarea'))
    expect(textAreas.length).toBeGreaterThanOrEqual(1)
    await setNativeValue(textAreas[0] as HTMLElement, '种子超龄作废')
    // 选择异常类型：点开唯一的 Select，再点「补种」选项
    const select = modal!.querySelector('.ant-select')
    expect(select).not.toBeNull()
    await act(async () => {
      ;(select as HTMLElement).dispatchEvent(
        new MouseEvent('mousedown', { bubbles: true }),
      )
      await new Promise((r) => setTimeout(r, 30))
    })
    const option = Array.from(
      document.querySelectorAll('.ant-select-item-option'),
    ).find((item) => item.textContent === '补种')
    expect(option).not.toBeNull()
    await act(async () => {
      ;(option as HTMLElement).dispatchEvent(
        new MouseEvent('mousedown', { bubbles: true }),
      )
      ;(option as HTMLElement).dispatchEvent(
        new MouseEvent('click', { bubbles: true }),
      )
      await new Promise((r) => setTimeout(r, 30))
    })
    const okButton = Array.from(modal!.querySelectorAll('button')).find(
      (btn) => btn.textContent?.replace(/\s/g, '') === '登记',
    )
    expect(okButton).not.toBeNull()
    await act(async () => {
      okButton!.click()
      await new Promise((r) => setTimeout(r, 60))
    })
    expect(actions.createScheduleAnomaly).toHaveBeenCalledWith(
      expect.objectContaining({
        product_code: 'FA',
        batch_no: 'FA26399',
        anomaly_type: 'reseeded',
        reason: '种子超龄作废',
      }),
    )
    // 成功后列表重新拉取
    expect(actions.getScheduleAnomalies).toHaveBeenCalled()
  })

  it('无查询权限时显示权限提示', async () => {
    clearProductionAuthForTest()
    await renderPage()
    const text = container.textContent ?? ''
    expect(text).toContain('未获得异常记录查看权限')
    expect(actions.getScheduleAnomalies).not.toHaveBeenCalled()
  })
})
