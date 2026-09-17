import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

const css = readFileSync(new URL('./globals.css', import.meta.url), 'utf8').replace(
  /\/\*[\s\S]*?\*\//g,
  '',
)

type CssRule = { selector: string; body: string }

function parseRules(source: string): CssRule[] {
  return [...source.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((match) => ({
    selector: match[1].trim(),
    body: match[2],
  }))
}

describe('globals.css 主按钮样式', () => {
  it('给 .ant-btn-primary 设背景的规则都排除 ghost 变体', () => {
    // ghost 主按钮文字用主色，实心背景会把文字盖成同色（按钮看起来"没字"）。
    // 回归：曾把 .ant-btn-primary 统一刷成实心紫，导致「做二级培训」等 ghost 按钮空白。
    const offenders = parseRules(css)
      .filter((rule) => rule.selector.includes('.ant-btn-primary'))
      .filter((rule) => /background\s*:/.test(rule.body))
      .filter((rule) => !rule.selector.includes('ant-btn-background-ghost'))
      .map((rule) => rule.selector)

    expect(offenders).toEqual([])
  })

  it('覆盖规则保持原优先级（:where 不提升特异性）', () => {
    const selectors = parseRules(css)
      .filter((rule) => rule.selector.includes('.ant-btn-primary'))
      .map((rule) => rule.selector)

    expect(selectors.length).toBeGreaterThan(0)
    expect(
      selectors.every((selector) =>
        /^\.ant-btn-primary:where\(:not\(\.ant-btn-background-ghost\)\)(:hover|:active)?$/.test(
          selector,
        ),
      ),
    ).toBe(true)
  })
})