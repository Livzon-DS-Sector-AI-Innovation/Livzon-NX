/* @vitest-environment happy-dom */
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { expect, it } from 'vitest'
import { PagePermissionDiff } from './PagePermissionDiff'

it('shows both sides of changes and immediate revocation impact', () => {
  const html = renderToStaticMarkup(<PagePermissionDiff impactNote="只影响当前用户" changes={[{
    pageKey: 'hr:employee-management:profile', pageName: '人事管理 · 员工管理',
    before: '角色基线；可查看', after: '用户覆盖；无权限', kind: 'revoke',
  }]} />)
  expect(html).toContain('调整前')
  expect(html).toContain('调整后')
  expect(html).toContain('用户覆盖；无权限')
  expect(html).toContain('撤销授权')
  expect(html).toContain('只影响当前用户')
  expect(html).toContain('Livzon 访问范围将过期')
})
