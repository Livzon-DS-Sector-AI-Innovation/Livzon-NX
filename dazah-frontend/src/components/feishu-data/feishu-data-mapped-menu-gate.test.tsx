import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

describe('feishu-data mapped menu gate contract', () => {
  const gateSource = fileURLToPath(
    new URL('./MappedMenuPageGate.tsx', import.meta.url),
  )
  const source = readFileSync(gateSource, 'utf8')

  it('activates mapped pages only for backend-ready modules', () => {
    // production 的后端 page-data 路由尚未提供，必须保持在启用集合之外，
    // 否则页面加载即产生错误横幅
    expect(source).toContain("const FEISHU_MODULES = new Set<FeishuModuleCode>(['energy', 'warehouse'])")
    expect(source).not.toMatch(/new Set<FeishuModuleCode>\(\[[^\]]*production/)
  })

  it('uses antd v6 prop names for loading and error surface', () => {
    // v6 弃用了 Spin tip 与 Alert message 标题语义
    expect(source).toContain('<Spin description=')
    expect(source).not.toContain('<Spin tip=')
    expect(source).toContain('title="读取页面数据映射失败')
    expect(source).not.toContain('message="读取页面数据映射失败')
  })
})
