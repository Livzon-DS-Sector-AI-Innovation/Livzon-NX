import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import GlobalError from './global-error'

describe('global error page', () => {
  it('shows a Chinese recovery path without a raw runtime message', () => {
    const markup = renderToStaticMarkup(React.createElement(GlobalError, {
      error: new Error('Failed to fetch'),
      unstable_retry: () => undefined,
    }))
    expect(markup).toContain('页面暂时无法显示')
    expect(markup).toContain('网络连接失败，请检查网络后重试')
    expect(markup).toContain('重试')
    expect(markup).not.toContain('Failed to fetch')
  })
})
