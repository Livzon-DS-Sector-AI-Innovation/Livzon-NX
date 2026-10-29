import { describe, expect, it } from 'vitest'

import nextConfig from '../../next.config'

describe('next config security headers', () => {
  it('ships a restrictive CSP and framing protection', async () => {
    const rules = await nextConfig.headers?.()
    const globalRule = rules?.find((rule) => rule.source === '/(.*)')
    expect(globalRule).toBeTruthy()

    const headers = Object.fromEntries(
      (globalRule?.headers ?? []).map(({ key, value }) => [key.toLowerCase(), value]),
    )

    expect(headers['content-security-policy']).toContain("default-src 'self'")
    expect(headers['content-security-policy']).toContain("frame-ancestors 'none'")
    expect(headers['content-security-policy']).toContain("object-src 'none'")
    expect(headers['content-security-policy']).toContain("script-src 'self' 'unsafe-inline'")
    // 飞书头像/图片走 CDN 域名，CSP 必须放行这些来源
    expect(headers['content-security-policy']).toContain('https://*.feishucdn.com')
    expect(headers['content-security-policy']).toContain('https://*.feishu.cn')
    expect(headers['x-frame-options']).toBe('DENY')
    expect(headers['x-content-type-options']).toBe('nosniff')
    expect(headers['referrer-policy']).toBe('strict-origin-when-cross-origin')
    expect(headers['strict-transport-security']).toContain('max-age=31536000')
  })

  it('disables framework disclosure and production source maps', () => {
    expect(nextConfig.poweredByHeader).toBe(false)
    expect(nextConfig.productionBrowserSourceMaps).toBe(false)
  })
})
