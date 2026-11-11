import { describe, expect, it } from 'vitest'

import {
  normalizePlanContent,
  normalizePlanDocument,
  planDocumentToPayload,
} from './emergencyPlanModel'

describe('emergencyPlanModel', () => {
  it('缺字段的历史数据归一化为完整结构', () => {
    const document = normalizePlanDocument({
      cover: { title: '预案' },
      organization: {
        commander: '史润',
        deputy_commanders: ['田成', '', 3],
        groups: [{ name: '应急处置组', leader: '朱少军' }, { leader: '无组名' }],
      },
      chapters: [{ key: 'scenario', title: '情景设置' }, { title: '无标识' }],
    })
    expect(document).not.toBeNull()
    expect(document!.cover).toEqual({
      company: '',
      title: '预案',
      level: '',
      drill_date: '',
      archive_date: '',
      archive_department: '',
    })
    expect(document!.organization.deputy_commanders).toEqual(['田成'])
    expect(document!.organization.groups).toEqual([
      { name: '应急处置组', leader: '朱少军', members: '', duties: '' },
    ])
    expect(document!.chapters).toEqual([
      { key: 'scenario', title: '情景设置', content: '' },
    ])
    expect(document!.workshop_organization).toBeNull()
    expect(normalizePlanDocument(null)).toBeNull()
    expect(normalizePlanDocument('bad')).toBeNull()
  })

  it('保存负载保留全部字段并带 schema 版本', () => {
    const document = normalizePlanDocument({
      preface: '引言',
      chapters: [{ key: 'guiding_thought', title: '指导思想', content: 'x' }],
    })!
    const payload = planDocumentToPayload(document)
    expect(payload.schema_version).toBe(1)
    expect(payload.preface).toBe('引言')
    expect(payload.chapters).toEqual(document.chapters)
  })

  it('内容负载：任务状态、审核报告与默认值', () => {
    const payload = normalizePlanContent({
      plan_id: 'p1',
      plan_name: '预案',
      revision_no: 4,
      ai_generated: true,
      job: { state: 'running', progress: '生成中' },
      last_review: {
        summary: '整体可用',
        score: 86,
        fixed_count: 3,
        dimensions: [{ name: '一致性', status: 'warn', note: 'n' }],
        issues: [{ status: 'fixed', section: 'scenario', problem: 'p', after: 'a' }],
      },
      content: { preface: '引言' },
    })
    expect(payload).not.toBeNull()
    expect(payload!.content_status).toBe('empty')
    expect(payload!.job).toEqual({ state: 'running', progress: '生成中' })
    expect(payload!.last_review?.score).toBe(86)
    expect(payload!.last_review?.needs_human_count).toBe(0)
    expect(payload!.last_review?.issues[0]).toMatchObject({
      id: 'issue-0',
      status: 'fixed',
      category: 'technical',
    })
    expect(payload!.content?.preface).toBe('引言')
    expect(normalizePlanContent(undefined)).toBeNull()
    const noReview = normalizePlanContent({ last_review: { summary: '无评分' } })
    expect(noReview!.last_review).toBeNull()
    expect(noReview!.job).toBeNull()
  })
})
