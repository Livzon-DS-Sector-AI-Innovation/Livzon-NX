/* @vitest-environment happy-dom */

import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  SafetyPageFeishuMirror: vi.fn((_props: Record<string, unknown>) => null),
}))

vi.mock('@/components/safety', () => ({
  SafetyPageFeishuMirror: mocks.SafetyPageFeishuMirror,
}))

// 五个镜像子页共用同一壳：只有 pageKey/pageName 不同
const cases: [string, string][] = [
  ['feeding-inspection', '投料巡查表'],
  ['centrifuge-discharge-inspection', '离心出料风险巡查表'],
  ['hazchem-unloading-inspection', '危险化学品卸车巡查表'],
  ['special-danger-work', '次日特殊危险作业审批'],
]

for (const [dir, pageName] of cases) {
  void dir
}

import FeedingInspectionPage from './page'

describe('feeding inspection mirror page', () => {
  it('renders the mirror with the feeding page key', async () => {
    const element = FeedingInspectionPage()
    renderToStaticMarkup(element)

    expect((mocks.SafetyPageFeishuMirror.mock.calls.at(-1) as unknown as [Record<string, unknown>] | undefined)?.[0]).toMatchObject({
      pageKey: 'safety:ops-safety:feeding-inspection',
      pageName: '投料巡查表',
    })
  })
})
