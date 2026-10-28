import { describe, expect, it, vi } from 'vitest'

vi.mock('@/lib/safety-page-tables', () => ({
  SAFETY_PAGE_TABLE_KEYS: {
    ehsChangeReview: 'safety:risk-hazard:ehs-change:ehs-change-review',
    ehsChangeAcceptance: 'safety:risk-hazard:ehs-change:ehs-change-acceptance',
  },
  SAFETY_PAGE_TABLE_PREFERRED_COLUMNS: {
    'safety:risk-hazard:ehs-change:ehs-change-review': [
      '申请编号',
      '变更名称',
      '变更级别',
    ],
    'safety:risk-hazard:ehs-change:ehs-change-acceptance': [
      '申请编号',
      '验收日期',
      '验收人',
    ],
  },
  SAFETY_PAGE_TABLE_CREATE_URLS: {
    'safety:risk-hazard:ehs-change:ehs-change-review':
      'https://applink.feishu.cn/T9aVmYNY9oKR',
    'safety:risk-hazard:ehs-change:ehs-change-acceptance':
      'https://applink.feishu.cn/T9aVn44berv1',
  },
}))

import AcceptancePage from '@/app/(dashboard)/safety/ehs-change/acceptance/page'
import ReviewPage from '@/app/(dashboard)/safety/ehs-change/page'

/** 页面返回 <div><SafetyPageFeishuMirror .../></div>，取镜像元素的 props 断言装配。 */
function mirrorProps(page: { props: { children: { props: unknown } } }) {
  return page.props.children.props as Record<string, unknown>
}

describe('EHS 变更镜像页路由', () => {
  it('review page binds the review page key and its preferred columns', async () => {
    const element = await ReviewPage()
    expect(mirrorProps(element)).toMatchObject({
      pageKey: 'safety:risk-hazard:ehs-change:ehs-change-review',
      pageName: 'EHS变更审批',
      preferredColumnNames: ['申请编号', '变更名称', '变更级别'],
      createUrl: 'https://applink.feishu.cn/T9aVmYNY9oKR',
    })
  })

  it('acceptance page binds the acceptance page key and its preferred columns', async () => {
    const element = await AcceptancePage()
    expect(mirrorProps(element)).toMatchObject({
      pageKey: 'safety:risk-hazard:ehs-change:ehs-change-acceptance',
      pageName: '变更验收审批',
      preferredColumnNames: ['申请编号', '验收日期', '验收人'],
      createUrl: 'https://applink.feishu.cn/T9aVn44berv1',
    })
  })
})
