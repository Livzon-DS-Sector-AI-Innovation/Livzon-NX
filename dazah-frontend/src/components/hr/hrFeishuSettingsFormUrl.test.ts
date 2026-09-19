import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

// HR 飞书设置的表单链接契约：
// 1) 实体保存后必须失效入职台账页的「新增」表单链接缓存（跨页实时同步）；
// 2) 入职台账页通过专用接口读取表单链接，且不再携带写死的表单地址。

const settingsPageSource = readFileSync(
  new URL('./HrFeishuSettingsPage.tsx', import.meta.url),
  'utf-8'
)
const onboardingPageSource = readFileSync(
  new URL('./onboarding-management/OnboardingManagementPage.tsx', import.meta.url),
  'utf-8'
)

describe('HR feishu settings form-url wiring', () => {
  it('entity save invalidates the onboarding form-url cache', () => {
    expect(settingsPageSource).toContain("queryKey: ['onboarding-form-url']")
  })

  it('onboarding page consumes the configured form url via the client helper', () => {
    expect(onboardingPageSource).toContain('fetchOnboardingFormUrl')
    // 表单地址属于部署数据：页面源码不允许再出现写死的表单 ID
    expect(onboardingPageSource).not.toMatch(/shrcn[A-Za-z0-9]{16,}/)
  })
})
