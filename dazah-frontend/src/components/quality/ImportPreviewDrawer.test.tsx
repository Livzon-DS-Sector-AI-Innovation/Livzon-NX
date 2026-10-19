/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { ConfigProvider } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ImportPreviewDrawer } from './ImportPreviewDrawer'

describe('ImportPreviewDrawer', () => {
  let root: Root
  let container: HTMLDivElement
  const preview = vi.fn(), confirm = vi.fn(), close = vi.fn(), success = vi.fn()
  const tick = () => new Promise(resolve => setTimeout(resolve, 40))
  const button = (label: string) => [...document.querySelectorAll<HTMLButtonElement>('button')]
    .find(node => node.textContent?.replace(/\s/g, '') === label)!
  const click = (label: string) => act(async () => { button(label).click(); await tick() })
  beforeEach(async () => {
    vi.clearAllMocks()
    preview.mockResolvedValue({ total_rows: 1, valid_rows: 1 })
    confirm.mockResolvedValue({ success_count: 1, update_count: 0, skip_count: 0, error_count: 0 })
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    await act(async () => {
      root.render(<ConfigProvider theme={{ token: { motion: false } }}><ImportPreviewDrawer isOpen
        title="导入测试台账" headers={['编号']} fileInputId="preview-test-file"
        templateDownloadUrl="/unused-template" templateFilename="template.docx"
        onClose={close} onSuccess={success} previewAction={preview} confirmAction={confirm} closeDelayMs={0} />
      </ConfigProvider>)
      await tick()
    })
  })
  afterEach(() => { act(() => root.unmount()); container.remove() })
  function select(name = '测试.docx') {
    const input = document.querySelector<HTMLInputElement>('#preview-test-file')!
    Object.defineProperty(input, 'files', { configurable: true, value: [new File(['test'], name)] })
    act(() => input.dispatchEvent(new Event('change', { bubbles: true })))
  }

  it('opens a named portal and cancellation never previews or imports', async () => {
    const dialog = document.querySelector('[role="dialog"]')!
    expect(dialog.textContent).toContain('导入测试台账')
    expect(container.contains(dialog)).toBe(false)
    select()
    await click('取消')
    expect(close).toHaveBeenCalledOnce()
    expect(preview).not.toHaveBeenCalled()
    expect(confirm).not.toHaveBeenCalled()
    expect(document.body.textContent).toContain('点击选择 Word 文件')
  })

  it('retains the preview and delegates the chosen file and duplicate policy on success', async () => {
    select()
    await click('预览数据')
    expect(document.body.textContent).toContain('导入预览')
    await click('确认导入')
    const [payload, skip, update] = confirm.mock.calls[0]
    expect(payload.get('file').name).toBe('测试.docx')
    expect([skip, update]).toEqual([true, false])
    expect(close).toHaveBeenCalledOnce()
    expect(success).toHaveBeenCalledOnce()
  })

  it('keeps the file and dialog after a failed import so the user can retry', async () => {
    confirm.mockRejectedValueOnce(new Error('导入失败，请核对文件'))
    select()
    await click('预览数据')
    await click('确认导入')
    expect(document.querySelector('[role="dialog"]')?.textContent).toContain('测试.docx')
    expect(document.body.textContent).toContain('导入失败')
    expect(close).not.toHaveBeenCalled()
    expect(success).not.toHaveBeenCalled()
    await click('确认导入')
    expect(confirm).toHaveBeenCalledTimes(2)
    expect(success).toHaveBeenCalledOnce()
  })

  it('shows partial failures and preserves the drawer instead of reporting a complete import', async () => {
    confirm.mockResolvedValueOnce({ success_count: 1, update_count: 0, skip_count: 0, error_count: 1,
      error_details: [{ row: 2, error: '编号重复' }] })
    select()
    await click('预览数据')
    await click('确认导入')
    expect(document.body.textContent).toContain('部分数据未导入')
    expect(document.body.textContent).toContain('第2行：编号重复')
    expect(close).not.toHaveBeenCalled()
    expect(success).toHaveBeenCalledOnce()
    expect(button('确认导入')).toBeUndefined()
  })
})
