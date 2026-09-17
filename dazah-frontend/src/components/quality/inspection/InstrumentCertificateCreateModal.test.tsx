/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const qualityActions = vi.hoisted(() => ({
  analyzeInstrumentCertificate: vi.fn(),
  rematchInstrumentCertificate: vi.fn(),
}))

vi.mock('@/actions/quality-inspection', () => qualityActions)

import { InstrumentCertificateCreateModal } from './InstrumentCertificateCreateModal'

const ANALYZE_RESULT = {
  extracted: {
    instrument_name: '电子天平',
    model: 'MS204S/01',
    serial_no: 'B303717218',
    calibration_date: '2025-06-03',
    next_calibration_date_stated: null,
    certificate_no: 'JC2025-0603-01',
    calibration_agency: '区计量院',
    conclusion: '合格',
  },
  directory: {
    matched: true,
    match_by: '器具编号',
    record_id: 'rec_dir_1',
    instrument_name: '电子天平',
    location: '二楼天平室QC-2-2-042',
    period_months: 24,
    period_text: '24',
  },
  computed_next_calibration_date: '2027-06-02',
  attachment_file_token: 'ft_cert',
  mapped_fields: {
    器具名称: '电子天平',
    器具编号: 'B303717218',
    检定日期: '2025-06-03',
    使用地点: '二楼天平室QC-2-2-042',
    附件: [{ file_token: 'ft_cert' }],
  },
  warnings: ['设备目录周期 24 个月与表内公式 12 个月不一致'],
}

function pngFile(): File {
  return new File([new Uint8Array([137, 80, 78, 71])], '证书.png', {
    type: 'image/png',
  })
}

let container: HTMLDivElement
let root: Root

beforeEach(() => {
  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
  document.body.replaceChildren()
  vi.clearAllMocks()
})

function renderModal(onApply: (mapped: Record<string, unknown>) => void) {
  act(() => {
    root.render(
      <App>
        <InstrumentCertificateCreateModal open onClose={vi.fn()} onApply={onApply} />
      </App>,
    )
  })
}

function findButton(text: string): HTMLButtonElement | undefined {
  return Array.from(document.querySelectorAll('button')).find(
    (node) => node.textContent === text,
  )
}

async function pickFile() {
  const input = document.querySelector('input[type="file"]')
  expect(input).toBeTruthy()
  await act(async () => {
    await Promise.resolve()
  })
  Object.defineProperty(input!, 'files', { value: [pngFile()] })
  input!.dispatchEvent(new Event('change', { bubbles: true }))
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 20))
  })
}

describe('InstrumentCertificateCreateModal 上传校准证书识别', () => {
  it('识别成功后展示结果，填入新增表单回调 mapped_fields', async () => {
    qualityActions.analyzeInstrumentCertificate.mockResolvedValue(ANALYZE_RESULT)
    const onApply = vi.fn()
    renderModal(onApply)

    // 未选文件时「开始识别」禁用
    expect(findButton('开始识别')?.disabled).toBe(true)

    await pickFile()
    expect(findButton('开始识别')?.disabled).toBe(false)

    await act(async () => {
      findButton('开始识别')!.click()
      await new Promise((resolve) => setTimeout(resolve, 20))
    })
    expect(qualityActions.analyzeInstrumentCertificate).toHaveBeenCalledTimes(1)
    expect(document.body.textContent).toContain('识别结果')
    // 关键字段渲染为可编辑输入框（值在 input value 里）
    const inputValues = Array.from(document.querySelectorAll('input')).map(
      (node) => (node as HTMLInputElement).value,
    )
    expect(inputValues).toContain('电子天平')
    expect(inputValues).toContain('B303717218')
    // 目录匹配信息在只读区文本里
    expect(document.body.textContent).toContain('二楼天平室QC-2-2-042')
    expect(document.body.textContent).toContain('2027-06-02')
    expect(document.body.textContent).toContain('24 个月')

    await act(async () => {
      findButton('填入新增表单')!.click()
      await new Promise((resolve) => setTimeout(resolve, 20))
    })
    expect(onApply).toHaveBeenCalledTimes(1)
    expect(onApply.mock.calls[0]?.[0]).toEqual(ANALYZE_RESULT.mapped_fields)
  })

  it('识别失败时透出错误信息且不回调', async () => {
    qualityActions.analyzeInstrumentCertificate.mockRejectedValue(
      new Error('AI 服务暂不可用'),
    )
    const onApply = vi.fn()
    renderModal(onApply)

    await pickFile()
    await act(async () => {
      findButton('开始识别')!.click()
      await new Promise((resolve) => setTimeout(resolve, 20))
    })

    expect(document.body.textContent).toContain('AI 服务暂不可用')
    expect(findButton('填入新增表单')).toBeUndefined()
    expect(onApply).not.toHaveBeenCalled()
  })

  it('识别提示（warnings）展示给用户核对', async () => {
    qualityActions.analyzeInstrumentCertificate.mockResolvedValue(ANALYZE_RESULT)
    renderModal(vi.fn())

    await pickFile()
    await act(async () => {
      findButton('开始识别')!.click()
      await new Promise((resolve) => setTimeout(resolve, 20))
    })

    expect(document.body.textContent).toContain('识别提示')
    expect(document.body.textContent).toContain('周期 24 个月')
  })
})

describe('InstrumentCertificateCreateModal 人工修正后重新匹配', () => {
  it('修改出厂编号后点重新匹配，填入表单用重新匹配后的字段', async () => {
    qualityActions.analyzeInstrumentCertificate.mockResolvedValue(ANALYZE_RESULT)
    qualityActions.rematchInstrumentCertificate.mockResolvedValue({
      ...ANALYZE_RESULT,
      extracted: { ...ANALYZE_RESULT.extracted, serial_no: 'QCPD-007' },
      directory: {
        matched: true,
        match_by: '仪表编号',
        record_id: 'rec_dir_2',
        instrument_name: '移液器',
        location: '抗生素效价室滴定间2',
        period_months: 12,
        period_text: '12',
      },
      computed_next_calibration_date: '2027-08-12',
      mapped_fields: {
        器具名称: '移液器',
        器具编号: 'QCPD-007',
        检定日期: '2025-06-03',
        使用地点: '抗生素效价室滴定间2',
        附件: [{ file_token: 'ft_cert' }],
      },
      warnings: [],
    })
    const onApply = vi.fn()
    renderModal(onApply)

    await pickFile()
    await act(async () => {
      findButton('开始识别')!.click()
      await new Promise((resolve) => setTimeout(resolve, 20))
    })

    // 修改出厂编号输入框
    const serialInput = Array.from(document.querySelectorAll('input')).find(
      (node) => (node as HTMLInputElement).value === 'B303717218',
    )
    expect(serialInput).toBeTruthy()
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype,
        'value',
      )?.set
      setter!.call(serialInput!, 'QCPD-007')
      serialInput!.dispatchEvent(new Event('input', { bubbles: true }))
      await new Promise((resolve) => setTimeout(resolve, 20))
    })

    await act(async () => {
      findButton('重新匹配')!.click()
      await new Promise((resolve) => setTimeout(resolve, 20))
    })
    expect(qualityActions.rematchInstrumentCertificate).toHaveBeenCalledTimes(1)
    const payload = qualityActions.rematchInstrumentCertificate.mock.calls[0]?.[0]
    expect(payload.serial_no).toBe('QCPD-007')
    expect(payload.attachment_file_token).toBe('ft_cert')

    // 重新匹配后展示新匹配到的目录地点
    expect(document.body.textContent).toContain('抗生素效价室滴定间2')

    await act(async () => {
      findButton('填入新增表单')!.click()
      await new Promise((resolve) => setTimeout(resolve, 20))
    })
    expect(onApply).toHaveBeenCalledTimes(1)
    expect(onApply.mock.calls[0]?.[0]).toEqual({
      器具名称: '移液器',
      器具编号: 'QCPD-007',
      检定日期: '2025-06-03',
      使用地点: '抗生素效价室滴定间2',
      附件: [{ file_token: 'ft_cert' }],
    })
  })
})

async function pickFileWith(file: File) {
  const input = document.querySelector('input[type="file"]')
  expect(input).toBeTruthy()
  await act(async () => {
    await Promise.resolve()
  })
  Object.defineProperty(input!, 'files', { value: [file] })
  input!.dispatchEvent(new Event('change', { bubbles: true }))
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 20))
  })
}

describe('InstrumentCertificateCreateModal 上传校验与关闭', () => {
  it('拒绝非 PDF/图片格式并提示', async () => {
    renderModal(vi.fn())
    const txt = new File(['data'], '证书.txt', { type: 'text/plain' })
    await pickFileWith(txt)
    expect(document.body.textContent).toContain(
      '仅支持 PDF / PNG / JPG 格式的校准证书',
    )
    expect(findButton('开始识别')?.disabled).toBe(true)
  })

  it('拒绝超过 20MB 的证书文件', async () => {
    renderModal(vi.fn())
    const big = new File(['x'], 'cert.png', { type: 'image/png' })
    Object.defineProperty(big, 'size', { value: 21 * 1024 * 1024 })
    await pickFileWith(big)
    expect(document.body.textContent).toContain('证书文件不能超过 20MB')
  })

  it('点关闭回调 onClose', async () => {
    const onClose = vi.fn()
    act(() => {
      root.render(
        <App>
          <InstrumentCertificateCreateModal
            open
            onClose={onClose}
            onApply={vi.fn()}
          />
        </App>,
      )
    })
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20))
    })
    // antd 两字中文按钮会在字符间插入空格（「关 闭」），按去空格文本匹配
    const closeBtn = Array.from(document.querySelectorAll('button')).find(
      (node) => node.textContent?.replace(/\s/g, '') === '关闭',
    )
    expect(closeBtn).toBeTruthy()
    await act(async () => {
      closeBtn!.click()
      await new Promise((resolve) => setTimeout(resolve, 20))
    })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('重新匹配失败时透出错误', async () => {
    qualityActions.analyzeInstrumentCertificate.mockResolvedValue(ANALYZE_RESULT)
    qualityActions.rematchInstrumentCertificate.mockRejectedValue(
      new Error('目录反查失败'),
    )
    renderModal(vi.fn())
    await pickFile()
    await act(async () => {
      findButton('开始识别')!.click()
      await new Promise((resolve) => setTimeout(resolve, 20))
    })
    await act(async () => {
      findButton('重新匹配')!.click()
      await new Promise((resolve) => setTimeout(resolve, 20))
    })
    expect(document.body.textContent).toContain('目录反查失败')
  })
})
