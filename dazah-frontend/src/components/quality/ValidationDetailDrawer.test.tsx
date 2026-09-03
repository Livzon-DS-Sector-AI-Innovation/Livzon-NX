/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { ValidationDetailDrawer } from './ValidationDetailDrawer'

let container: HTMLElement
let root: Root

function renderDrawer(record: Record<string, unknown> | null, open = true) {
  act(() => {
    root.render(
      <App>
        <ValidationDetailDrawer
          open={open}
          record={record}
          onClose={() => {}}
        />
      </App>,
    )
  })
}

describe('ValidationDetailDrawer', () => {
  beforeEach(() => {
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
  })

  it('renders structured participants and owner with avatars', () => {
    renderDrawer({
      title: '生化培养箱再确认',
      participants: [
        { name: '张三', avatar_url: 'https://a/x.png', id: 'ou_1' },
        { name: '李四', id: 'ou_2' },
      ],
      owner_name: [{ name: '王五', avatar_url: 'https://a/y.png', id: 'ou_3' }],
    })
    const text = document.body.textContent || ''
    expect(text).toContain('生化培养箱再确认')
    expect(text).toContain('张三')
    expect(text).toContain('李四')
    expect(text).toContain('王五')
  })

  it('renders structured group chat with group name', () => {
    renderDrawer({
      title: '工艺验证方案',
      group_chat: [{ id: 'oc_1', name: '验证群', avatar_url: 'https://a/g.png' }],
    })
    const text = document.body.textContent || ''
    expect(text).toContain('验证群')
  })

  it('joins plain string person/group arrays and falls back to dash', () => {
    renderDrawer({
      title: '清洁验证',
      participants: '赵六',
      group_chat: ['验证A群', '验证B群'],
    })
    const text = document.body.textContent || ''
    expect(text).toContain('赵六')
    expect(text).toContain('验证A群、验证B群')
  })

  it('shows dash when record is null', () => {
    renderDrawer(null)
    const text = document.body.textContent || ''
    expect(text).toContain('-')
  })
})
