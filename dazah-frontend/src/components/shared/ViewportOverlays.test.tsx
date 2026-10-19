/* @vitest-environment happy-dom */
import { act, useState, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App, Button, ConfigProvider, DatePicker, Drawer, Modal, Popconfirm, Select, theme } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ViewportOverlays from './ViewportOverlays'
import styles from './viewport-overlays.module.css'

describe('ViewportOverlays', () => {
  let root: Root
  let container: HTMLDivElement
  const tick = () => new Promise(resolve => setTimeout(resolve, 40))
  const click = async (element: HTMLElement) => act(async () => { element.click(); await tick() })
  const button = (label: string) => [...document.querySelectorAll<HTMLButtonElement>('button')]
    .find(el => el.textContent?.replace(/\s/g, '') === label)!
  async function render(children: ReactNode, dark = false) {
    await act(async () => {
      root.render(<ConfigProvider theme={{ algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm, token: { motion: false } }}>
        <ViewportOverlays>{children}</ViewportOverlays>
      </ConfigProvider>)
      await tick()
    })
  }
  beforeEach(() => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })
  afterEach(() => { act(() => root.unmount()); container.remove() })

  it('keeps modal portal bounds and custom body styles, and cancels without saving', async () => {
    const save = vi.fn()
    function Editor() {
      const [open, setOpen] = useState(true)
      return <Modal open={open} title="编辑记录" styles={{ body: { paddingTop: 12 } }}
        onOk={save} onCancel={() => setOpen(false)} cancelText="取消" destroyOnHidden><input defaultValue="保留输入" /></Modal>
    }
    await render(<Editor />)
    const dialog = document.querySelector('.ant-modal')!
    expect(container.contains(dialog)).toBe(false)
    expect(dialog.closest('.ant-modal-root')?.classList.contains(styles.modal)).toBe(true)
    expect(dialog.querySelector('.ant-modal-body')?.classList.contains(styles.body)).toBe(true)
    expect((dialog.querySelector('.ant-modal-body') as HTMLElement).style.paddingTop).toBe('12px')
    expect(dialog.querySelector('.ant-modal-footer')?.classList.contains(styles.footer)).toBe(true)
    await click(button('取消'))
    expect(document.querySelector('.ant-modal')).toBeNull()
    expect(save).not.toHaveBeenCalled()
  })

  it('also bounds App.useApp confirmation portals and retains confirm/cancel behavior', async () => {
    const confirm = vi.fn()
    function Trigger() {
      const { modal } = App.useApp()
      return <Button onClick={() => modal.confirm({ title: '删除测试记录？', content: '删除后不可恢复', onOk: confirm, okText: '删除', cancelText: '取消' })}>打开</Button>
    }
    await render(<Trigger />)
    await click(button('打开'))
    expect(document.querySelector('.ant-modal-body')?.classList.contains(styles.body)).toBe(true)
    await click(button('取消'))
    expect(confirm).not.toHaveBeenCalled()
    await click(button('打开'))
    await click(button('删除'))
    expect(confirm).toHaveBeenCalledTimes(1)
  })

  it('preserves nested confirmation behavior and removes portals when the scope unmounts', async () => {
    const confirm = vi.fn()
    await render(<Modal open footer={null} title="详情"><Popconfirm title="删除该记录？" onConfirm={confirm} cancelText="取消">
      <Button>删除记录</Button></Popconfirm></Modal>)
    await click(button('删除记录'))
    const popup = document.querySelector('.ant-popconfirm')!
    expect(popup.classList.contains(styles.floating)).toBe(true)
    await click(button('取消'))
    expect(confirm).not.toHaveBeenCalled()
    await render(null)
    expect(document.querySelector('.ant-popconfirm')).toBeNull()
    expect(document.querySelector('.ant-modal')).toBeNull()
  })

  it('updates an open form theme immediately without losing its draft', async () => {
    function Editor() {
      const { token } = theme.useToken()
      return <Modal open title="编辑记录" footer={null}>
        <input aria-label="草稿" defaultValue="原始内容" />
        <span data-testid="form-text" style={{ color: token.colorText }}>内容</span>
      </Modal>
    }
    await render(<Editor />)
    const input = document.querySelector<HTMLInputElement>('input[aria-label="草稿"]')!
    input.value = '尚未保存的修改'
    const light = (document.querySelector('[data-testid="form-text"]') as HTMLElement).style.color
    await render(<Editor />, true)
    expect(document.querySelector('input[aria-label="草稿"]')).toBe(input)
    expect(input.value).toBe('尚未保存的修改')
    expect((document.querySelector('[data-testid="form-text"]') as HTMLElement).style.color).not.toBe(light)
    expect(document.querySelector('.ant-modal-body')?.classList.contains(styles.body)).toBe(true)
  })

  it.each([false, true])('keeps drawer actions and picker/select portals under the inherited theme (dark=%s)', async dark => {
    function Fields() {
      const { token } = theme.useToken()
      return <Drawer open title="详情" footer={<Button>保存</Button>} styles={{ body: { padding: 12 } }}>
        <span data-testid="theme" style={{ color: token.colorText }}>继承主题</span>
        <DatePicker open /><Select open value="one" options={[{ value: 'one', label: '候选项' }]} />
      </Drawer>
    }
    await render(<Fields />, dark)
    expect(document.querySelector('.ant-drawer-body')?.classList.contains(styles.drawerBody)).toBe(true)
    expect(document.querySelector('.ant-drawer-footer')?.classList.contains(styles.footer)).toBe(true)
    expect(document.querySelector('.ant-picker-dropdown')?.classList.contains(styles.datePicker)).toBe(true)
    expect(document.querySelector('.ant-select-dropdown')?.classList.contains(styles.select)).toBe(true)
    const expected = document.createElement('span')
    expected.style.color = theme.getDesignToken({ algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm }).colorText
    expect((document.querySelector('[data-testid="theme"]') as HTMLElement).style.color).toBe(expected.style.color)
  })
})
