/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getGuardianRoster: vi.fn(),
  createGuardianRoster: vi.fn(),
  updateGuardianRoster: vi.fn(),
  deleteGuardianRoster: vi.fn(),
  exportGuardianRoster: vi.fn(),
  canOperate: true,
  canDelete: true,
  canAccess: true,
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

vi.mock('@/actions/safety', () => ({
  getGuardianRoster: mocks.getGuardianRoster,
  createGuardianRoster: mocks.createGuardianRoster,
  updateGuardianRoster: mocks.updateGuardianRoster,
  deleteGuardianRoster: mocks.deleteGuardianRoster,
  exportGuardianRoster: mocks.exportGuardianRoster,
}))

vi.mock('@/hooks/usePagePermissions', () => ({
  usePagePermissions: () => ({
    canAccess: mocks.canAccess,
    canQuery: mocks.canAccess,
    canOperate: mocks.canOperate,
    canDelete: mocks.canDelete,
    canApprove: false,
    canReject: false,
  }),
}))

vi.mock('@/components/safety/GuardianRosterImportModal', () => ({
  default: () => null,
}))

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>()
  return { ...actual, message: mocks.message }
})

vi.mock('@ant-design/icons', () => {
  const Icon = () => null
  return {
    ImportOutlined: Icon,
    DownloadOutlined: Icon,
    PlusOutlined: Icon,
  }
})

import { GuardianRosterPanel } from './GuardianRosterPanel'

const WORKSHOPS = [
  { workshop: '103车间', count: 2 },
  { workshop: '设备动力部', count: 1 },
]

const ROWS = [
  {
    id: 'gr1',
    person_name: '张三',
    workshop: '103车间',
    phone: '13800000000',
    position: '消毒',
    score: 85,
    exam_name: '监护人考试',
    exam_date: '2026-10-22',
    remark: null,
    source_file: '名单.xlsx',
  },
  {
    id: 'gr2',
    person_name: '李四',
    workshop: '103车间',
    phone: null,
    position: '机修',
    score: 78,
    exam_name: '监护人考试',
    exam_date: '2026-10-23',
    remark: null,
    source_file: '名单.xlsx',
  },
  {
    id: 'gr3',
    person_name: '王五',
    workshop: '设备动力部',
    phone: '13900000000',
    position: '电工',
    score: 90,
    exam_name: '监护人考试2',
    exam_date: '2026-10-29',
    remark: null,
    source_file: '名单.xlsx',
  },
]

let root: Root | undefined

function flush(ms = 60) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function buttons(text: string) {
  return Array.from(
    document.body.querySelectorAll<HTMLButtonElement>('button'),
  ).filter((b) => b.textContent?.replace(/\s/g, '').includes(text))
}

beforeEach(() => {
  mocks.getGuardianRoster.mockImplementation((_params) =>
    Promise.resolve({
      code: 200,
      data: { items: ROWS, total: ROWS.length, workshops: WORKSHOPS },
    })
  )
  mocks.createGuardianRoster.mockResolvedValue({ code: 200, data: { id: 'n1' } })
  mocks.updateGuardianRoster.mockResolvedValue({ code: 200, data: { id: 'gr1' } })
  mocks.deleteGuardianRoster.mockResolvedValue({ code: 200, data: null })
})

afterEach(async () => {
  if (root) {
    await act(async () => {
      root!.unmount()
    })
    root = undefined
  }
  document.body.replaceChildren()
  vi.clearAllMocks()
})

async function renderPanel(
  props: { initialList?: unknown; initialError?: string | null } = {},
) {
  const container = document.body.appendChild(document.createElement('div'))
  await act(async () => {
    root = createRoot(container)
    root!.render(
      <GuardianRosterPanel
        initialList={
          (props.initialList ?? {
            items: ROWS,
            total: ROWS.length,
            workshops: WORKSHOPS,
          }) as never
        }
        initialError={props.initialError ?? null}
      />,
    )
  })
  await flush()
}

describe('监护人名单面板', () => {
  it('渲染车间计数卡片与名单表格', async () => {
    await renderPanel()
    expect(document.body.textContent).toContain('全部车间：3')
    expect(document.body.textContent).toContain('103车间：2')
    expect(document.body.textContent).toContain('设备动力部：1')
    expect(document.body.textContent).toContain('张三')
    expect(document.body.textContent).toContain('共 3 人')
  })

  it('点选车间卡片按车间过滤', async () => {
    await renderPanel()
    await act(async () => {
      buttons('103车间：2')[0].click()
    })
    await flush()
    expect(mocks.getGuardianRoster).toHaveBeenLastCalledWith(
      expect.objectContaining({ workshop: '103车间', page: 1 }),
    )
  })

  it('初始加载失败时展示错误与重试', async () => {
    await renderPanel({ initialList: null, initialError: '监护人名单加载失败' })
    expect(document.body.textContent).toContain('监护人名单加载失败')
    const retry = buttons('重试')[0]
    expect(retry).toBeTruthy()
    await act(async () => {
      retry!.click()
    })
    await flush()
    expect(mocks.getGuardianRoster).toHaveBeenCalled()
  })

  it('编辑回填并保存', async () => {
    await renderPanel()
    await act(async () => {
      const edit = Array.from(document.body.querySelectorAll('a')).find(
        (a) => a.textContent === '编辑',
      )
      edit!.click()
    })
    await flush()
    expect(document.body.textContent).toContain('编辑监护人：张三')
    await act(async () => {
      buttons('保存')[0].click()
    })
    await flush()
    expect(mocks.updateGuardianRoster).toHaveBeenCalledWith(
      'gr1',
      expect.objectContaining({ person_name: '张三', workshop: '103车间' }),
      'safety:ops-safety:guardian-roster',
    )
    expect(mocks.message.success).toHaveBeenCalledWith('监护人已更新')
  })

  it('删除监护人需 Popconfirm 确认', async () => {
    await renderPanel()
    await act(async () => {
      const del = Array.from(document.body.querySelectorAll('a')).find(
        (a) => a.textContent === '删除',
      )
      del!.click()
    })
    await flush()
    const ok = buttons('OK')
    expect(ok.length).toBeGreaterThan(0)
    await act(async () => {
      ok[ok.length - 1].click()
    })
    await flush()
    expect(mocks.deleteGuardianRoster).toHaveBeenCalledWith(
      'gr1',
      'safety:ops-safety:guardian-roster',
    )
    expect(mocks.message.success).toHaveBeenCalledWith('已删除')
  })

  it('导出 Excel：按当前筛选调用导出 action 并触发下载', async () => {
    const createObjectURL = vi.fn(() => 'blob:mock')
    const revokeObjectURL = vi.fn()
    Object.defineProperty(window.URL, 'createObjectURL', {
      value: createObjectURL,
      configurable: true,
    })
    Object.defineProperty(window.URL, 'revokeObjectURL', {
      value: revokeObjectURL,
      configurable: true,
    })
    mocks.exportGuardianRoster.mockResolvedValue({
      code: 0,
      message: 'ok',
      data: btoa('fake-xlsx'),
    })
    await renderPanel()
    const exportButton = buttons('导出Excel')[0]
    expect(exportButton, '导出按钮应存在').toBeTruthy()
    await act(async () => {
      exportButton!.click()
    })
    await flush()
    expect(mocks.exportGuardianRoster).toHaveBeenCalledWith(
      { workshop: null, keyword: null },
      'safety:ops-safety:guardian-roster',
    )
    expect(createObjectURL).toHaveBeenCalledTimes(1)
    expect(mocks.message.success).toHaveBeenCalledWith('导出成功')
  })

  it('无操作权限时隐藏导入/新建入口', async () => {
    mocks.canOperate = false
    mocks.canDelete = false
    try {
      await renderPanel()
      expect(buttons('Excel导入').length).toBe(0)
      expect(buttons('新建监护人').length).toBe(0)
      expect(
        Array.from(document.body.querySelectorAll('a')).find(
          (a) => a.textContent === '删除',
        ),
      ).toBeUndefined()
    } finally {
      mocks.canOperate = true
      mocks.canDelete = true
    }
  })
})
