/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  fetchPositionTransfers: vi.fn(),
  searchFeishuMembers: vi.fn(),
}))

const actionMocks = vi.hoisted(() => ({
  createPositionTransfer: vi.fn(),
  updatePositionTransfer: vi.fn(),
  deletePositionTransfer: vi.fn(),
  syncPositionTransferFromFeishuAction: vi.fn(),
  submitPositionTransferApproval: vi.fn(),
}))

const permissionMocks = vi.hoisted(() => ({
  canOperate: false,
  canDelete: false,
  canExport: false,
  canSync: false,
}))

vi.mock('@/lib/api/client/hr', () => apiMocks)
vi.mock('@/actions/hr', () => actionMocks)
vi.mock('@/hooks/usePagePermissions', () => ({
  usePagePermissions: () => permissionMocks,
}))

import PositionTransferClient from './PositionTransferClient'
import type { PositionTransferRecord } from '@/types/hr'

// 联系电话/申请人确认说明/申请人签名/确认日期 只允许出现在详情抽屉，列表不得展示
const record: PositionTransferRecord = {
  id: 'pt-1',
  employee_name: '张三',
  employee_number: 'E001',
  employee_id: 'emp-1',
  department_before: '质量部',
  original_position: '检验员',
  effective_date: '2026-10-01',
  apply_department: '生产部',
  apply_position: '工艺员',
  contact_phone: '13800001234',
  applicant_confirmation_text: '本人已知晓并确认交接安排',
  applicant_signature: '张三（签名）',
  applicant_confirmation_date: '2026-09-20',
  approval_status: '草稿',
}

const listResponse = {
  data: [record],
  meta: { page: 1, page_size: 20, total: 1 },
}

function renderInApp(element: React.ReactNode) {
  const container = document.createElement('div')
  document.body.appendChild(container)
  const root = createRoot(container)
  const settle = async (ms = 80) => {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, ms))
    })
  }
  act(() => {
    root.render(<App>{element}</App>)
  })
  return { container, root, settle }
}

function tableHeaders(container: HTMLElement): string[] {
  return Array.from(container.querySelectorAll('.ant-table-thead th')).map(
    (th) => (th.textContent || '').trim(),
  )
}

describe('PositionTransferClient 申请人确认字段只在详情展示', () => {
  let root: Root | null = null
  let container: HTMLElement | null = null

  beforeEach(() => {
    apiMocks.fetchPositionTransfers.mockResolvedValue(listResponse)
  })

  afterEach(() => {
    act(() => root?.unmount())
    container?.remove()
    document.body
      .querySelectorAll('.ant-drawer, .ant-modal-root, .ant-select-dropdown, .ant-message')
      .forEach((node) => node.remove())
    vi.clearAllMocks()
  })

  it('列表不渲染联系电话/申请人确认说明/申请人签名/确认日期列，也不泄露字段值', async () => {
    const rendered = renderInApp(
      <PositionTransferClient initialRecords={[record]} initialTotal={1} />,
    )
    root = rendered.root
    container = rendered.container
    await rendered.settle()

    const headers = tableHeaders(container)
    for (const header of [
      '申请人',
      '原部门',
      '原职位',
      '生效日期',
      '申请部门',
      '申请职位',
      '审批状态',
      '操作',
    ]) {
      expect(headers).toContain(header)
    }
    for (const hidden of ['联系电话', '申请人确认说明', '申请人签名', '确认日期']) {
      expect(headers).not.toContain(hidden)
    }

    const text = container.textContent || ''
    expect(text).toContain('张三')
    expect(text).toContain('质量部')
    expect(text).not.toContain('13800001234')
    expect(text).not.toContain('本人已知晓并确认交接安排')
    expect(text).not.toContain('张三（签名）')
    expect(text).not.toContain('2026-09-20')
  })

  it('点击申请人打开详情抽屉，展示联系电话、确认说明、签名与确认日期', async () => {
    const rendered = renderInApp(
      <PositionTransferClient initialRecords={[record]} initialTotal={1} />,
    )
    root = rendered.root
    container = rendered.container
    await rendered.settle()

    const applicantLink = container.querySelector('.ant-table-tbody a') as HTMLElement | null
    expect(applicantLink).toBeTruthy()
    await act(async () => {
      applicantLink?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 200))
    })

    const drawerText = document.body.textContent || ''
    expect(drawerText).toContain('联系电话')
    expect(drawerText).toContain('13800001234')
    expect(drawerText).toContain('确认说明')
    expect(drawerText).toContain('本人已知晓并确认交接安排')
    expect(drawerText).toContain('签名')
    expect(drawerText).toContain('张三（签名）')
    expect(drawerText).toContain('确认日期')
    expect(drawerText).toContain('2026-09-20')
  })
})
