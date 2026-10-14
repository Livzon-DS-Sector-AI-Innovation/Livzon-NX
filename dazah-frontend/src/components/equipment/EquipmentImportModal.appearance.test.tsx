/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, it, vi } from 'vitest'
import { AntdProvider } from '../AntdProvider'
import { setAppearance } from '@/lib/useAppearance'
import { EquipmentImportModal } from './EquipmentImportModal'

vi.mock('antd', async (importOriginal) => {
  const actual = await importOriginal<typeof import('antd')>()
  return { ...actual, Upload: { ...actual.Upload, Dragger: ({ beforeUpload }: { beforeUpload: (file: File) => void }) =>
    <button onClick={() => beforeUpload(new File(['test'], '设备.xlsx'))}>选择测试台账</button>,
  } }
})

it('keeps the import instructions on a theme surface inside a dark modal', async () => {
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ code: 200,
    data: { total_rows: 1, created: 1, updated: 0, failed: 0, failures: [] },
  }) }))
  try {
    await act(async () => root.render(<AntdProvider><EquipmentImportModal open onClose={() => {}} onImported={() => {}} /></AntdProvider>))
    await act(async () => setAppearance('dark'))
    await act(async () => [...document.querySelectorAll('button')].find((button) => button.textContent === '选择测试台账')?.click())
    await act(async () => [...document.querySelectorAll('button')].find((button) => button.textContent?.includes('开始导入'))?.click())
    const modal = document.querySelector('.ant-modal')
    expect(modal?.textContent).toContain('导入')
    const note = [...(modal?.querySelectorAll<HTMLElement>('[style]') ?? [])].find((element) =>
      element.style.background === 'var(--color-surface-soft)')
    expect(note).toBeTruthy()
    expect(note?.textContent).toContain('新建 1 台')
    await act(async () => setAppearance('system'))
  } finally {
    await act(async () => root.unmount())
    host.remove()
    window.localStorage.clear()
    vi.unstubAllGlobals()
  }
})
