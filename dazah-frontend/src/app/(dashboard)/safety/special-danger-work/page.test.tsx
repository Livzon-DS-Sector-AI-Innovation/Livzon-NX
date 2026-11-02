import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  SafetyPageFeishuMirror: vi.fn((_props: Record<string, unknown>) => null),
}))

vi.mock('@/components/safety', () => ({
  SafetyPageFeishuMirror: mocks.SafetyPageFeishuMirror,
}))

import Page from './page'
import {
  SAFETY_PAGE_TABLE_CREATE_URLS,
  SAFETY_PAGE_TABLE_KEYS,
} from '@/lib/safety-page-tables'

describe('次日特殊危险作业审批 mirror page', () => {
  it('renders the mirror with the specialDangerWork page key', () => {
    renderToStaticMarkup(Page())

    expect((mocks.SafetyPageFeishuMirror.mock.calls.at(-1) as unknown as [Record<string, unknown>] | undefined)?.[0]).toMatchObject({
      pageKey: 'safety:ops-safety:special-danger-work',
      pageName: '次日特殊危险作业审批',
    })
  })

  it('passes the Feishu form create url for this page', () => {
    renderToStaticMarkup(Page())

    expect(
      (mocks.SafetyPageFeishuMirror.mock.calls.at(-1) as unknown as [Record<string, unknown>] | undefined)?.[0],
    ).toMatchObject({
      createUrl:
        SAFETY_PAGE_TABLE_CREATE_URLS[SAFETY_PAGE_TABLE_KEYS.specialDangerWork],
    })
  })
})
