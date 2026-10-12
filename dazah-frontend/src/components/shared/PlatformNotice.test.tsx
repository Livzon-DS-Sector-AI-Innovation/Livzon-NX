/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { Button, ConfigProvider, theme } from 'antd'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { antdTheme } from '@/lib/antd-theme'
import PlatformNotice from './PlatformNotice'

let root: Root
let host: HTMLDivElement

beforeEach(() => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
})

afterEach(async () => {
  await act(async () => root.unmount())
  host.remove()
  vi.unstubAllGlobals()
})

function rulesButton() {
  return document.querySelector<HTMLButtonElement>('[data-platform-notice] .ant-btn-link')!
}

it.each(['info', 'success', 'warning', 'error'] as const)('uses the theme %s colors, an icon, a concise body and rules entry', async (type) => {
  await act(async () => root.render(<ConfigProvider theme={antdTheme}>
    <PlatformNotice type={type} title="权限配置状态" description="完整的规则说明" showIcon={false}
      icon={<span>旧图标</span>} style={{ background: 'black', borderColor: 'black' }} />
  </ConfigProvider>))
  const notice = document.querySelector<HTMLElement>('[data-platform-notice]')!
  expect(notice.classList.contains(`ant-alert-${type}`)).toBe(true)
  expect(notice.classList.contains('ant-alert-with-description')).toBe(false)
  expect(notice.querySelector('.ant-alert-icon .anticon')).toBeTruthy()
  expect(notice.textContent).not.toContain('旧图标')
  expect(notice.textContent).toContain('权限配置状态')
  expect(notice.textContent).not.toContain('完整的规则说明')
  expect(rulesButton().textContent).toContain('了解访问规则')
  const token = theme.getDesignToken(antdTheme)
  const backgrounds = { info: token.colorInfoBg, success: token.colorSuccessBg, warning: token.colorWarningBg, error: token.colorErrorBg }
  const expected = document.createElement('div')
  expected.style.background = backgrounds[type]
  expect(notice.style.background).toBe(expected.style.background)
  expect(notice.style.borderColor).toBe('transparent')
})

it('opens the complete current rules without invoking recovery or write actions', async () => {
  const retry = vi.fn()
  await act(async () => root.render(<ConfigProvider theme={{ token: { motion: false } }}><PlatformNotice type="error" title="用户列表加载失败"
    description={<div><p>本地更改已保留，请重试。</p><ul><li>用户覆盖优先于角色基线</li></ul></div>}
    action={<Button onClick={retry}>重试</Button>} /></ConfigProvider>))
  await act(async () => rulesButton().click())
  const dialog = document.querySelector<HTMLElement>('.ant-modal')!
  expect(dialog.textContent).toContain('本地更改已保留，请重试。')
  expect(dialog.textContent).toContain('用户覆盖优先于角色基线')
  expect(dialog.textContent).toContain('不修改权限或业务数据')
  expect(retry).not.toHaveBeenCalled()
  await act(async () => document.querySelector<HTMLButtonElement>('.ant-modal-footer button')!.click())
  expect(document.querySelector('.ant-modal')).toBeNull()
  const retryButton = [...document.querySelectorAll('button')].find((button) => button.textContent?.replace(/\s/g, '') === '重试')!
  await act(async () => retryButton.click())
  expect(retry).toHaveBeenCalledOnce()
})

it('reuses an existing read-only rules dialog and honors its disabled state', async () => {
  const openRules = vi.fn()
  await act(async () => root.render(<PlatformNotice title="角色权限基线" onLearnRules={openRules} rulesDisabled />))
  expect(rulesButton().disabled).toBe(true)
  await act(async () => rulesButton().click())
  expect(openRules).not.toHaveBeenCalled()
  await act(async () => root.render(<PlatformNotice title="角色权限基线" onLearnRules={openRules} />))
  await act(async () => rulesButton().click())
  expect(openRules).toHaveBeenCalledOnce()
  expect(document.querySelector('.ant-modal')).toBeNull()
})

it('preserves dismissing a notice and supports legacy message summaries', async () => {
  const close = vi.fn()
  await act(async () => root.render(<PlatformNotice message="同步已完成" type="success" closable onClose={close} />))
  expect(document.querySelector('[data-platform-notice]')?.textContent).toContain('同步已完成')
  await act(async () => document.querySelector<HTMLButtonElement>('.ant-alert-close-icon')!.click())
  expect(close).toHaveBeenCalledOnce()
})

it('opens standalone notices without requiring an App provider', async () => {
  await act(async () => root.render(<PlatformNotice title="登录状态已失效，请重新发起授权。" type="error" />))
  await act(async () => rulesButton().click())
  expect(document.querySelector('.ant-modal')?.textContent).toContain('登录状态已失效，请重新发起授权。')
})

it('hides the rules entry when showRulesLink is disabled', async () => {
  await act(async () => root.render(<PlatformNotice type="info" title="法规雷达 · 上次扫描发现 2 部新法规" showRulesLink={false} />))
  const notice = document.querySelector<HTMLElement>('[data-platform-notice]')!
  expect(notice.textContent).toContain('法规雷达')
  expect(notice.querySelector('.ant-btn-link')).toBeNull()
  expect(document.querySelector('.ant-modal')).toBeNull()
})
