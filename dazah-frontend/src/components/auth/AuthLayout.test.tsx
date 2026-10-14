import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import { APPEARANCE_STORAGE_KEY } from '@/lib/appearance'
import { setAppearance } from '@/lib/useAppearance'
import { AntdProvider } from '@/components/AntdProvider'

import { AuthLayout } from './AuthLayout'

describe('AuthLayout', () => {
  it('shows the product identity without the obsolete internal-system badge', () => {
    const markup = renderToStaticMarkup(
      <AuthLayout>
        <div>登录表单</div>
      </AuthLayout>,
    )

    expect(markup).toContain('原料药工厂管理平台')
    expect(markup).toContain('登录表单')
    expect(markup).toContain('仅限已授权人员使用')
    expect(markup).not.toContain('内部系统')
    expect(markup).toContain('data-appearance="fixed-light"')
    expect(markup).toContain('科技赋能制药 守护人类健康')
    expect(markup).toContain('aria-label="平台业务能力"')
    for (const label of ['生产协同', '质量管控', '设备与安全']) {
      expect(markup).toContain(label)
    }
    expect(markup).toContain('高效 · 合规 · 安全 · 可持续')
  })

  it.each(['dark', 'system'])('keeps authentication light with a saved %s preference and a dark system', async (mode) => {
    window.localStorage.setItem(APPEARANCE_STORAGE_KEY, mode)
    vi.spyOn(window, 'matchMedia').mockReturnValue({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() } as unknown as MediaQueryList)
    const host = document.createElement('div')
    document.body.append(host)
    const root = createRoot(host)
    function Palette({ id }: { id: string }) {
      const { token } = theme.useToken()
      return <span data-testid={id} data-background={token.colorBgContainer} data-text={token.colorText} />
    }
    try {
      await act(async () => root.render(<>
        <AuthLayout><Palette id="auth" /></AuthLayout>
        <AntdProvider><Palette id="dashboard" /></AntdProvider>
      </>))
      expect(host.querySelector('[data-testid="auth"]')?.getAttribute('data-background')).toBe('#ffffff')
      expect(host.querySelector('[data-testid="auth"]')?.getAttribute('data-text')).toBe('#1a1a1a')
      expect(host.querySelector('[data-testid="dashboard"]')?.getAttribute('data-background')).toBe('#222225')
      expect(window.localStorage.getItem(APPEARANCE_STORAGE_KEY)).toBe(mode)
      await act(async () => setAppearance('light'))
      await act(async () => setAppearance('dark'))
      expect(host.querySelector('[data-testid="auth"]')?.getAttribute('data-background')).toBe('#ffffff')
      expect(host.querySelector('[data-testid="dashboard"]')?.getAttribute('data-background')).toBe('#222225')
      expect(window.localStorage.getItem(APPEARANCE_STORAGE_KEY)).toBe('dark')
    } finally {
      await act(async () => root.unmount())
      host.remove()
      window.localStorage.clear()
      delete document.documentElement.dataset.theme
      delete document.documentElement.dataset.appearance
      vi.restoreAllMocks()
    }
  })
})
/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { theme } from 'antd'
