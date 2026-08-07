import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

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
  })
})
