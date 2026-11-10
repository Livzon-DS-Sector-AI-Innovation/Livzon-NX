/** 应急预案 AI 工作台：本地结构化模型与归一化工具。

生成类型（@/types/generated/schema）的字段全部可选，直接在组件里使用会产生
大量 undefined 收窄；这里定义运行时恒有的规范化形态，并负责把接口返回
（可能缺字段的历史数据）转换为该形态。
 */

import type { components } from '@/types/generated/schema'

export interface PlanCover {
  company: string
  title: string
  level: string
  drill_date: string
  archive_date: string
  archive_department: string
}

export interface PlanOrgGroup {
  name: string
  leader: string
  members: string
  duties: string
}

export interface PlanOrganization {
  commander: string
  commander_duties: string
  deputy_commanders: string[]
  deputy_duties: string
  groups: PlanOrgGroup[]
}

export interface PlanWorkshopOrganization {
  department: string
  commander: string
  deputy_commander: string
  groups: PlanOrgGroup[]
}

export interface PlanChapter {
  key: string
  title: string
  content: string
}

export interface PlanDocument {
  cover: PlanCover
  preface: string
  organization: PlanOrganization
  workshop_organization: PlanWorkshopOrganization | null
  chapters: PlanChapter[]
}

export interface PlanContentPayload {
  plan_id: string
  plan_name: string
  content_status: string
  revision_no: number
  ai_generated: boolean
  content: PlanDocument | null
  job: { state: string; progress: string } | null
  last_review: {
    summary: string
    score: number
    fixed_count: number
    needs_human_count: number
    dimensions: { name: string; status: string; note: string }[]
    issues: {
      id: string
      status: string
      category: string
      section: string
      problem: string
      after: string
    }[]
  } | null
}

type GeneratedDocument = components['schemas']['EmergencyPlanDocument']

function str(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function groups(value: unknown): PlanOrgGroup[] {
  if (!Array.isArray(value)) return []
  return value
    .filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null)
    .map((item) => ({
      name: str(item.name),
      leader: str(item.leader),
      members: str(item.members),
      duties: str(item.duties),
    }))
    .filter((item) => item.name)
}

function organization(value: unknown): PlanOrganization {
  const raw = (typeof value === 'object' && value !== null ? value : {}) as Record<
    string,
    unknown
  >
  const deputies = Array.isArray(raw.deputy_commanders)
    ? raw.deputy_commanders.filter(
        (item): item is string => typeof item === 'string' && item.length > 0
      )
    : []
  return {
    commander: str(raw.commander),
    commander_duties: str(raw.commander_duties),
    deputy_commanders: deputies,
    deputy_duties: str(raw.deputy_duties),
    groups: groups(raw.groups),
  }
}

function workshop(value: unknown): PlanWorkshopOrganization | null {
  if (typeof value !== 'object' || value === null) return null
  const raw = value as Record<string, unknown>
  return {
    department: str(raw.department),
    commander: str(raw.commander),
    deputy_commander: str(raw.deputy_commander),
    groups: groups(raw.groups),
  }
}

/** 接口返回的正文 → 规范化文档；结构非法时返回 null。 */
export function normalizePlanDocument(
  raw: GeneratedDocument | unknown | null | undefined
): PlanDocument | null {
  if (typeof raw !== 'object' || raw === null) return null
  const source = raw as Record<string, unknown>
  const coverSource = (typeof source.cover === 'object' && source.cover !== null
    ? source.cover
    : {}) as Record<string, unknown>
  const chapters = Array.isArray(source.chapters)
    ? source.chapters
        .filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null)
        .map((item) => ({
          key: str(item.key),
          title: str(item.title),
          content: str(item.content),
        }))
        .filter((item) => item.key)
    : []
  return {
    cover: {
      company: str(coverSource.company),
      title: str(coverSource.title),
      level: str(coverSource.level),
      drill_date: str(coverSource.drill_date),
      archive_date: str(coverSource.archive_date),
      archive_department: str(coverSource.archive_department),
    },
    preface: str(source.preface),
    organization: organization(source.organization),
    workshop_organization: workshop(source.workshop_organization),
    chapters,
  }
}

/** 规范化文档 → 保存接口负载（字段与生成类型结构兼容）。 */
export function planDocumentToPayload(document: PlanDocument): GeneratedDocument {
  return {
    schema_version: 1,
    cover: document.cover,
    preface: document.preface,
    organization: document.organization,
    workshop_organization: document.workshop_organization,
    chapters: document.chapters,
  }
}

interface RawContentPayload {
  plan_id?: unknown
  plan_name?: unknown
  content_status?: unknown
  revision_no?: unknown
  ai_generated?: unknown
  content?: unknown
  job?: unknown
  last_review?: unknown
}

/** 接口返回 → 规范化内容负载（含审核报告的最小形态）。 */
export function normalizePlanContent(
  raw: unknown
): PlanContentPayload | null {
  if (typeof raw !== 'object' || raw === null) return null
  const source = raw as RawContentPayload
  const job =
    typeof source.job === 'object' && source.job !== null
      ? (source.job as Record<string, unknown>)
      : null
  const review =
    typeof source.last_review === 'object' && source.last_review !== null
      ? (source.last_review as Record<string, unknown>)
      : null
  const reviewIssues =
    review && Array.isArray(review.issues)
      ? review.issues.filter(
          (item): item is Record<string, unknown> => typeof item === 'object' && item !== null
        )
      : []
  const reviewDimensions =
    review && Array.isArray(review.dimensions)
      ? review.dimensions.filter(
          (item): item is Record<string, unknown> => typeof item === 'object' && item !== null
        )
      : []
  return {
    plan_id: str(source.plan_id),
    plan_name: str(source.plan_name),
    content_status: str(source.content_status) || 'empty',
    revision_no:
      typeof source.revision_no === 'number' ? source.revision_no : 0,
    ai_generated: source.ai_generated === true,
    content: normalizePlanDocument(source.content),
    job:
      job && str(job.state)
        ? { state: str(job.state), progress: str(job.progress) }
        : null,
    last_review:
      review && typeof review.score === 'number'
        ? {
            summary: str(review.summary),
            score: review.score,
            fixed_count: typeof review.fixed_count === 'number' ? review.fixed_count : 0,
            needs_human_count:
              typeof review.needs_human_count === 'number'
                ? review.needs_human_count
                : 0,
            dimensions: reviewDimensions.map((item) => ({
              name: str(item.name),
              status: str(item.status) || 'ok',
              note: str(item.note),
            })),
            issues: reviewIssues.map((item, index) => ({
              id: str(item.id) || `issue-${index}`,
              status: str(item.status) || 'unresolved',
              category: str(item.category) || 'technical',
              section: str(item.section),
              problem: str(item.problem),
              after: str(item.after),
            })),
          }
        : null,
  }
}
