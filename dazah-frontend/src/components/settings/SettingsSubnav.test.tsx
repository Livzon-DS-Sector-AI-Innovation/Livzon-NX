/* @vitest-environment happy-dom */

import { act, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, expect, it } from 'vitest'
import SettingsSubnav from './SettingsSubnav'

const host = document.createElement('div')
document.body.append(host)
const root = createRoot(host)

afterEach(async () => {
  await act(async () => root.render(null))
})

it('switches the visible settings subpage and marks its navigation entry', async () => {
  function Example() {
    const [activeKey, setActiveKey] = useState('first')
    return <SettingsSubnav
      ariaLabel="测试子导航"
      activeKey={activeKey}
      onChange={setActiveKey}
      items={[
        { key: 'first', label: '第一项', icon: <span>一</span>, children: <p>第一页内容</p> },
        { key: 'second', label: '第二项', icon: <span>二</span>, children: <p>第二页内容</p> },
      ]}
    />
  }

  await act(async () => root.render(<Example />))
  expect(host.querySelector('nav[aria-label="测试子导航"] [aria-current="page"]')?.textContent).toContain('第一项')
  expect(host.textContent).toContain('第一页内容')
  await act(async () => (Array.from(host.querySelectorAll('button')).find((item) => item.textContent?.includes('第二项')))?.click())
  expect(host.querySelector('nav[aria-label="测试子导航"] [aria-current="page"]')?.textContent).toContain('第二项')
  expect(host.textContent).toContain('第二页内容')
  expect(host.textContent).not.toContain('第一页内容')
})

it('uses the full card width when a menu has no secondary navigation', async () => {
  await act(async () => root.render(<SettingsSubnav
    ariaLabel="单页导航"
    activeKey="only"
    onChange={() => {}}
    showNav={false}
    items={[{ key: 'only', label: '单页', icon: null, children: <p>单页内容</p> }]}
  />))
  expect(host.querySelector('nav')).toBeNull()
  expect(host.textContent).toContain('单页内容')
})
