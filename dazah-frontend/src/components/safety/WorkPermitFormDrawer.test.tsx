/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getWorkPermitMeta: vi.fn(),
  getWorkCertificates: vi.fn(),
  getCertificateCategories: vi.fn(),
  createWorkPermit: vi.fn(),
  updateWorkPermit: vi.fn(),
  updateWorkCertificate: vi.fn(),
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}))

vi.mock('@/actions/safety', () => ({
  getWorkPermitMeta: mocks.getWorkPermitMeta,
  getWorkCertificates: mocks.getWorkCertificates,
  getCertificateCategories: mocks.getCertificateCategories,
  createWorkPermit: mocks.createWorkPermit,
  updateWorkPermit: mocks.updateWorkPermit,
  updateWorkCertificate: mocks.updateWorkCertificate,
}))

// 组件使用 antd 静态 message；只替换副作用边界，其余保持真实渲染。
// happy-dom 下 rc-picker 的 dayjs 适配器缺 isValid：局部 stub DatePicker 为受控 input。
vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>()
  const { createElement } = await import('react')
  const DatePickerStub = (props: Record<string, unknown>) =>
    createElement('input', {
      'data-testid': 'date-picker-stub',
      value: (props.value as string) ?? '',
      onChange: props.onChange,
    })
  return {
    ...actual,
    DatePicker: Object.assign(DatePickerStub, { RangePicker: DatePickerStub }),
    message: mocks.message,
  }
})

vi.mock('@ant-design/icons', () => {
  const Icon = () => null
  return { PlusOutlined: Icon }
})

import { WorkPermitFormDrawer } from './WorkPermitFormDrawer'

const META = {
  permit_types: [{ value: 'hot_work', label: '动火作业', no_prefix: 'DH' }],
  level_options: {
    hot_work: [
      { value: 'special', label: '特级' },
      { value: 'grade2', label: '二级' },
    ],
  },
  person_roles: {
    hot_work: [
      { role: 'applicant', label: '申请人', cert: false },
      { role: 'guardian', label: '监护人', cert: true },
    ],
  },
  measures: {
    hot_work: [
      { key: 'm1', text: '清理周边可燃物', fill_keys: ['具体距离'] },
      { key: 'm2', text: '办理动火证' },
    ],
  },
  type_fields: {},
  risk_identification_options: ['动火产生火花', '有限空间作业'],
  gas_types: ['hot_work'],
  gas_cycle_minutes: { hot_work: 60 },
  certificate_categories: [],
}

const EDITING = {
  id: 'p1',
  permit_type: 'hot_work',
  permit_level: 'grade2',
  apply_department: '一车间',
  work_description: '罐区动火',
  work_location: '罐区东',
  work_unit: '维修班',
  planned_start_time: null,
  planned_end_time: null,
  persons: [{ role: 'applicant', name: '张三' }],
  risk_identifications: ['动火产生火花'],
  safety_measures: [{ key: 'm1', status: 'yes', fills: {} }],
  type_data: {},
  related_legacy_no_text: null,
  remark: null,
}

function flush(ms = 80) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function textInputs() {
  return Array.from(document.body.querySelectorAll<HTMLInputElement>('input'))
    .filter((node) => node.type !== 'checkbox')
    .filter((node) => node.getAttribute('data-testid') !== 'date-picker-stub')
}

function dateInputs() {
  return Array.from(
    document.body.querySelectorAll<HTMLInputElement>(
      'input[data-testid="date-picker-stub"]',
    ),
  )
}

async function setInputValue(node: HTMLInputElement, value: string) {
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      'value',
    )?.set
    setter?.call(node, value)
    node.dispatchEvent(new Event('input', { bubbles: true }))
  })
}

async function clickButton(text: string) {
  const button = Array.from(
    document.body.querySelectorAll<HTMLButtonElement>('button'),
  ).find((b) => b.textContent?.replace(/\s/g, '').includes(text))
  expect(button, `button ${text} 应存在`).toBeTruthy()
  await act(async () => {
    button!.click()
  })
  await flush(30)
}

beforeEach(() => {
  mocks.getWorkPermitMeta.mockResolvedValue({ code: 200, data: META })
  mocks.getWorkCertificates.mockResolvedValue({
    code: 200,
    data: {
      items: [
        {
          id: 'c1',
          person_name: '李四',
          certificate_no: 'DJ-001',
          certificate_category: 'electrician',
          status: 'valid',
        },
      ],
    },
  })
  mocks.getCertificateCategories.mockResolvedValue({
    code: 200,
    data: { categories: [{ value: 'electrician', label: '电工' }] },
  })
  mocks.createWorkPermit.mockResolvedValue({ code: 200, data: { id: 'new1' } })
  mocks.updateWorkPermit.mockResolvedValue({ code: 200, data: { id: 'p1' } })
})

afterEach(() => {
  if (root) await_act_unmount(root)
  root = undefined
  document.body.replaceChildren()
  vi.clearAllMocks()
})

let root: Root | undefined

async function await_act_unmount(r: Root) {
  await act(async () => {
    r.unmount()
  })
}

async function renderDrawer(props: Record<string, unknown>) {
  const container = document.body.appendChild(document.createElement('div'))
  await act(async () => {
    root = createRoot(container)
    root!.render(
      <WorkPermitFormDrawer
        {...(props as unknown as React.ComponentProps<typeof WorkPermitFormDrawer>)}
      />,
    )
  })
  await flush()
}

describe('作业票表单抽屉', () => {
  it('打开时加载模板与证件候选并渲染表单骨架', async () => {
    await renderDrawer({ open: true, onClose: () => {}, onCreated: () => {} })
    expect(document.body.textContent).toContain('新建作业票')
    expect(mocks.getWorkPermitMeta).toHaveBeenCalled()
    expect(mocks.getWorkCertificates).toHaveBeenCalled()
    expect(mocks.getCertificateCategories).toHaveBeenCalled()
    expect(document.body.textContent).toContain('风险辨识结果')
    expect(document.body.textContent).toContain('动火产生火花')
  })

  it('未选票种提交给出提示且不调用创建', async () => {
    const onClose = vi.fn()
    await renderDrawer({ open: true, onClose })
    await clickButton('保存草稿')
    expect(mocks.message.warning).toHaveBeenCalledWith('请选择票种')
    expect(mocks.createWorkPermit).not.toHaveBeenCalled()
    expect(onClose).not.toHaveBeenCalled()
  })

  it('编辑模式回填、勾选措施与人员后提交更新', async () => {
    const onClose = vi.fn()
    const onCreated = vi.fn()
    await renderDrawer({ open: true, onClose, onCreated, editing: EDITING })
    expect(document.body.textContent).toContain('编辑作业票')
    // 基础字段回填
    const location = textInputs().find((n) => n.value === '罐区东')
    expect(location).toBeTruthy()
    // 必填时间通过受控 stub 填入
    const dates = dateInputs()
    expect(dates.length).toBe(2)
    await setInputValue(dates[0], '2026-11-10 08:00:00')
    await setInputValue(dates[1], '2026-11-10 18:00:00')
    // 勾选第二条风险
    const riskBox = Array.from(
      document.body.querySelectorAll<HTMLInputElement>('input[type="checkbox"]'),
    ).find((n) => n.closest('label')?.textContent?.includes('有限空间作业'))
    expect(riskBox).toBeTruthy()
    await act(async () => {
      riskBox!.click()
    })
    // 编辑夹具中 m1 初始为 yes：先切「不适用」再切回「是」，验证填空项出现
    await clickButton('不适用')
    await clickButton('是')
    const fill = document.body.querySelector<HTMLInputElement>(
      'input[placeholder="具体距离"]',
    )
    expect(fill).toBeTruthy()
    await setInputValue(fill!, '5米')
    // 措施二改「不适用」（第二个不适用按钮）
    const notApplicable = Array.from(
      document.body.querySelectorAll<HTMLButtonElement>('button'),
    ).filter((b) => b.textContent?.replace(/\s/g, '') === '不适用')
    expect(notApplicable.length).toBe(2)
    await act(async () => {
      notApplicable[1].click()
    })
    await flush(30)
    // 添加监护人
    await clickButton('添加人员')
    expect(document.body.textContent).toContain('监护人')
    await clickButton('保存草稿')
    expect(mocks.updateWorkPermit).toHaveBeenCalledWith(
      'p1',
      expect.objectContaining({
        permit_type: 'hot_work',
        permit_level: 'grade2',
        work_location: '罐区东',
        risk_identifications: expect.arrayContaining(['动火产生火花', '有限空间作业']),
        safety_measures: expect.arrayContaining([
          expect.objectContaining({
            key: 'm1',
            status: 'yes',
            fills: expect.objectContaining({ 具体距离: '5米' }),
          }),
          expect.objectContaining({ key: 'm2', status: 'not_applicable' }),
        ]),
        persons: expect.arrayContaining([
          expect.objectContaining({ role: 'applicant', name: '张三' }),
          expect.objectContaining({ role: 'guardian' }),
        ]),
      }),
    )
    expect(mocks.message.success).toHaveBeenCalledWith('作业票已更新')
    expect(onCreated).toHaveBeenCalled()
    expect(onClose).toHaveBeenCalled()
  })

  it('更新失败提示错误且不关闭抽屉', async () => {
    mocks.updateWorkPermit.mockResolvedValue({ code: 500, message: '后端异常' })
    const onClose = vi.fn()
    await renderDrawer({ open: true, onClose, editing: EDITING })
    const dates = dateInputs()
    await setInputValue(dates[0], '2026-11-10 08:00:00')
    await setInputValue(dates[1], '2026-11-10 18:00:00')
    await clickButton('保存草稿')
    expect(mocks.message.error).toHaveBeenCalledWith('后端异常')
    expect(onClose).not.toHaveBeenCalled()
  })

  it('取消按钮触发 onClose', async () => {
    const onClose = vi.fn()
    await renderDrawer({ open: true, onClose })
    await clickButton('取消')
    expect(onClose).toHaveBeenCalled()
  })
})
