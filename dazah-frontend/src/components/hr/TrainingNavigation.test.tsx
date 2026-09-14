/* @vitest-environment happy-dom */
import { act, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  push: vi.fn(), create: vi.fn(),
  message: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
  form: { setFieldValue: vi.fn(), resetFields: vi.fn() },
}))
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: mocks.push }) }))
vi.mock('@/lib/api/hr', () => ({ fetchEmployees: async () => ({ data: [{ employee_number: 'E01', name: '测试人员' }] }) }))
vi.mock('@/lib/api/client/hr', () => ({
  fetchTrainingDepartments: async () => ['测试部门'],
  fetchAnnualTrainingPlans: async () => ({ data: [
    { id: 'company-plan', year: 2026, department: '公司', plan_level: '公司级' },
    { id: 'department-plan', year: 2026, department: '测试部门', plan_level: '部门级' },
  ] }),
}))
vi.mock('@/actions/hr', () => ({ createTrainingLedgerPage: mocks.create,
  createAnnualTrainingPlan: vi.fn(), deleteAnnualTrainingPlan: vi.fn(), importAnnualTrainingPlan: vi.fn() }))
vi.mock('antd', () => {
  const Wrap = ({ children }: { children?: ReactNode }) => <div>{children}</div>
  const Form = Object.assign(({ children, onFinish }: { children?: ReactNode; onFinish?: (v: { employee_number: string }) => void }) =>
    <form onSubmit={(e) => { e.preventDefault(); onFinish?.({ employee_number: 'E01' }) }}>{children}</form>,
  { Item: Wrap, useForm: () => [mocks.form] })
  return {
    App: { useApp: () => ({ message: mocks.message }) }, Form,
    Card: Wrap, Row: Wrap, Col: Wrap, Spin: () => null, Popconfirm: Wrap,
    Modal: () => null, Upload: Wrap, Input: Wrap, AutoComplete: Wrap,
    Select: ({ onChange }: { onChange?: (v: string) => void }) => <button type="button" onClick={() => onChange?.('测试部门')}>选择部门</button>,
    Button: ({ children, htmlType, onClick }: { children?: ReactNode; htmlType?: 'submit'; onClick?: () => void }) =>
      <button type={htmlType ?? 'button'} onClick={onClick}>{children}</button>,
  }
})
import TrainingLedgerNewClient from './TrainingLedgerNewClient'
import AnnualPlanListClient from './AnnualPlanListClient'

afterEach(() => vi.clearAllMocks())

it.each([false, true])('navigates to the employee ledger after create or duplicate (%s)', async (duplicate) => {
  mocks.create.mockReset()
  if (duplicate) mocks.create.mockRejectedValue(new Error('已存在'))
  else mocks.create.mockResolvedValue({})
  const container = document.createElement('div')
  const root = createRoot(container)
  try {
    await act(async () => root.render(<TrainingLedgerNewClient />))
    await act(async () => container.querySelector('button')?.click())
    await act(async () => container.querySelector('form')?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })))
    expect(mocks.create).toHaveBeenCalledWith({ employee_number: 'E01', employee_name: '测试人员' })
    expect(mocks.push).toHaveBeenCalledWith('/hr/training/ledger?employee_number=E01')
  } finally { act(() => root.unmount()) }
})

it('navigates from company and department annual plan cards', async () => {
  const container = document.createElement('div')
  const root = createRoot(container)
  try {
    await act(async () => root.render(<AnnualPlanListClient />))
    const cards = container.querySelectorAll<HTMLDivElement>('div.cursor-pointer')
    expect(cards).toHaveLength(2)
    for (const card of cards) act(() => card.click())
    expect(mocks.push).toHaveBeenCalledWith('/hr/training/annual-plan?id=company-plan')
    expect(mocks.push).toHaveBeenCalledWith('/hr/training/annual-plan?id=department-plan')
  } finally { act(() => root.unmount()) }
})
