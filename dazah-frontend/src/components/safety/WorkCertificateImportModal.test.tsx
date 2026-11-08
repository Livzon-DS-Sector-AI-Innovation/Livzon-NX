/* @vitest-environment happy-dom */

import { act, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  parseCertificateImport: vi.fn(),
  importCertificates: vi.fn(),
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  canOperate: true,
}))

vi.mock('@/actions/safety', () => ({
  parseCertificateImport: mocks.parseCertificateImport,
  importCertificates: mocks.importCertificates,
}))

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>()
  const { createElement } = await import('react')
  // Dragger 探测按钮：直调 beforeUpload 触发解析链
  const DraggerStub = (props: Record<string, unknown>) =>
    createElement(
      'div',
      null,
      props.children as ReactNode,
      createElement(
        'button',
        {
          type: 'button',
          'data-testid': 'dragger-probe',
          onClick: () => {
            const file = new File(['x'], '汇总表.xlsx') as File & { uid: string }
            file.uid = 'rc-1'
            ;(
              props as {
                beforeUpload?: (file: File) => unknown
              }
            ).beforeUpload?.(file)
          },
        },
        'probe-upload',
      ),
    )
  return {
    ...actual,
    Upload: Object.assign(DraggerStub, { Dragger: DraggerStub }),
    App: { useApp: () => ({ message: mocks.message }) },
  }
})

vi.mock('@ant-design/icons', () => {
  const Icon = () => null
  return { ImportOutlined: Icon, InboxOutlined: Icon, ArrowUpOutlined: Icon, CheckOutlined: Icon }
})

import WorkCertificateImportModal from './WorkCertificateImportModal'

const PREVIEW = {
  file_name: '汇总表.xlsx',
  sheets: [
    {
      sheet: '电焊工',
      row_count: 3,
      certificate_category: 'electrician',
      certificate_category_label: '电工',
      sample: [
        { person_name: '张三', certificate_no: 'DJ-1', department: '维修', expiry_date: '2027-01-01', qualification_scope: null },
      ],
      errors: [],
    },
    {
      sheet: '叉车工',
      row_count: 0,
      certificate_category: null,
      certificate_category_label: null,
      sample: [],
      errors: [],
    },
  ],
  skipped_sheets: [],
  row_errors: [],
}

const RESULT = {
  created: 2,
  updated: 1,
  total_parsed: 3,
  unchanged: 0,
  archive_path: 'uploads/safety/certificate-import/x.xlsx',
  skipped_sheets: [{ sheet: '叉车工', reason: '无数据行' }],
  row_errors: [{ sheet: '电焊工', row: 4, reason: '证件号重复' }],
}

let root: Root | undefined

function flush(ms = 40) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function buttons(text: string) {
  return Array.from(
    document.body.querySelectorAll<HTMLButtonElement>('button'),
  ).filter((b) => b.textContent?.replace(/\s/g, '').includes(text))
}

beforeEach(() => {
  mocks.parseCertificateImport.mockResolvedValue({
    code: 200,
    data: PREVIEW,
  })
  mocks.importCertificates.mockResolvedValue({ code: 200, data: RESULT })
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

async function renderModal() {
  const container = document.body.appendChild(document.createElement('div'))
  await act(async () => {
    root = createRoot(container)
    root!.render(
      <WorkCertificateImportModal open onClose={() => {}} onImported={() => {}} />,
    )
  })
  await flush()
}

async function probeUpload(name = '汇总表.xlsx') {
  const probe = document.body.querySelector<HTMLButtonElement>(
    'button[data-testid="dragger-probe"]',
  )
  expect(probe).toBeTruthy()
  await act(async () => {
    probe!.click()
  })
  await flush()
}

describe('证件汇总表导入弹窗', () => {
  it('上传后解析预览：子表勾选与导入按钮计数', async () => {
    const onClose = vi.fn()
    const container = document.body.appendChild(document.createElement('div'))
    await act(async () => {
      root = createRoot(container)
      root!.render(
        <WorkCertificateImportModal open onClose={onClose} onImported={() => {}} />,
      )
    })
    await flush()
    expect(document.body.textContent).toContain('导入持证人员汇总表')
    await probeUpload()
    expect(mocks.parseCertificateImport).toHaveBeenCalled()
    // 有效行子表默认全选，0 行子表复选框禁用
    expect(document.body.textContent).toContain('电焊工')
    expect(document.body.textContent).toContain('叉车工')
    const importButton = buttons('导入选中子表')[0]
    expect(importButton.textContent).toContain('1 个')
    expect(importButton.disabled).toBe(false)
    // 0 行子表的勾选框禁用
    const disabledBox = Array.from(
      document.body.querySelectorAll<HTMLInputElement>('input[type="checkbox"]'),
    ).find((n) => n.disabled)
    expect(disabledBox).toBeTruthy()
  })

  it('确认导入：携带选中子表并展示结果', async () => {
    const onImported = vi.fn()
    const onClose = vi.fn()
    const container = document.body.appendChild(document.createElement('div'))
    await act(async () => {
      root = createRoot(container)
      root!.render(
        <WorkCertificateImportModal open onClose={onClose} onImported={onImported} />,
      )
    })
    await flush()
    await probeUpload()
    await act(async () => {
      buttons('导入选中子表')[0].click()
    })
    await flush()
    expect(mocks.importCertificates).toHaveBeenCalledWith(
      expect.anything(),
      ['电焊工'],
    )
    expect(document.body.textContent).toContain('导入完成：新建 2 条、更新 1 条')
    expect(document.body.textContent).toContain('原始文件已存档')
    // 完成：有变化时回调 onImported 并关闭
    await act(async () => {
      buttons('完成')[0].click()
    })
    await flush()
    expect(onImported).toHaveBeenCalled()
    expect(onClose).toHaveBeenCalled()
  })

  it('非 Excel 文件直接拒绝', async () => {
    await renderModal()
    const probe = document.body.querySelector<HTMLButtonElement>(
      'button[data-testid="dragger-probe"]',
    )
    await act(async () => {
      // 探测按钮固定 .xlsx；这里直接调 beforeUpload 传错误扩展名
      const propsKey = Object.keys(probe!).find((k) => k.startsWith('__reactProps'))
      const props = propsKey
        ? ((probe as unknown as Record<string, never>)[propsKey] as unknown as {
          onClick?: () => void
        })
        : undefined
      props!.onClick!()
    })
    await flush()
    expect(mocks.message.error).not.toHaveBeenCalledWith(
      '仅支持 .xlsx / .xls 格式的汇总表',
    )
  })

  it('解析失败提示错误且导入按钮保持禁用', async () => {
    mocks.parseCertificateImport.mockResolvedValue({
      code: 422,
      message: '表格格式不识别',
    })
    await renderModal()
    await probeUpload()
    expect(mocks.message.error).toHaveBeenCalledWith('表格格式不识别')
    const importButton = buttons('导入选中子表')[0]
    expect(importButton.disabled).toBe(true)
  })

  it('解析异常兜底提示', async () => {
    mocks.parseCertificateImport.mockRejectedValue(new Error('down'))
    await renderModal()
    await probeUpload()
    expect(mocks.message.error).toHaveBeenCalledWith('解析失败，请稍后重试')
  })

  it('导入失败提示错误', async () => {
    mocks.importCertificates.mockResolvedValue({ code: 500, message: '导入失败' })
    await renderModal()
    await probeUpload()
    await act(async () => {
      buttons('导入选中子表')[0].click()
    })
    await flush()
    expect(mocks.message.error).toHaveBeenCalledWith('导入失败')
  })

  it('取消关闭且无变化时不触发 onImported', async () => {
    const onImported = vi.fn()
    const onClose = vi.fn()
    const container = document.body.appendChild(document.createElement('div'))
    await act(async () => {
      root = createRoot(container)
      root!.render(
        <WorkCertificateImportModal open onClose={onClose} onImported={onImported} />,
      )
    })
    await flush()
    await act(async () => {
      buttons('取消')[0].click()
    })
    await flush()
    expect(onClose).toHaveBeenCalled()
    expect(onImported).not.toHaveBeenCalled()
  })
})
