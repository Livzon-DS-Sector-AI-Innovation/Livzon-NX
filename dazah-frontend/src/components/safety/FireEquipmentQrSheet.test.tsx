/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('qrcode.react', async () => {
  const { createElement } = await import('react')
  return {
    QRCodeCanvas: ({ value }: { value: string }) =>
      createElement('canvas', { 'data-qr-value': value }),
    QRCodeSVG: ({ value }: { value: string }) =>
      createElement('svg', { 'data-qr-value': value }),
  }
})

import FireEquipmentQrSheet, {
  fireEquipmentScanUrl,
  type FireEquipmentQrItem,
} from './FireEquipmentQrSheet'

const ITEMS: FireEquipmentQrItem[] = [
  {
    id: 'eq-1',
    equipmentTypeLabel: '灭火器',
    equipmentNo: 'MQC-001',
    department: '103三车间',
    location: '罐区西侧',
  },
]

describe('fireEquipmentScanUrl', () => {
  it('拼出扫码点检路由绝对地址', () => {
    expect(fireEquipmentScanUrl('eq-9')).toBe(
      `${window.location.origin}/safety/fire-inspection/scan/eq-9`,
    )
  })
})

describe('FireEquipmentQrSheet', () => {
  let root: ReturnType<typeof createRoot>
  let container: HTMLElement

  beforeEach(() => {
    vi.stubGlobal('print', vi.fn())
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('打开后渲染每台器材的点检卡（类型/编号/部门/位置 + 二维码）', async () => {
    act(() => {
      root.render(
        <App>
          <FireEquipmentQrSheet open onClose={() => {}} items={ITEMS} />
        </App>,
      )
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30))
    })
    const text = document.body.textContent ?? ''
    expect(text).toContain('灭火器点检卡')
    expect(text).toContain('MQC-001')
    expect(text).toContain('103三车间')
    expect(text).toContain('罐区西侧')
    expect(document.body.querySelector('svg')).toBeTruthy()
  })

  it('关闭状态不渲染点检卡', async () => {
    act(() => {
      root.render(
        <App>
          <FireEquipmentQrSheet open={false} onClose={() => {}} items={ITEMS} />
        </App>,
      )
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30))
    })
    expect((document.body.textContent ?? '').includes('灭火器点检卡')).toBe(false)
  })
})
