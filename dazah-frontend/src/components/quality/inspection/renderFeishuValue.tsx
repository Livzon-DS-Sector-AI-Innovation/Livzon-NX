import type { ReactNode } from 'react'
import { qualityTokens } from '../themeTokens'
import { Avatar, Space } from 'antd'
import type { App } from 'antd'
import dayjs from 'dayjs'

type FeishuMessage = ReturnType<typeof App.useApp>['message']

export interface FeishuAttachment {
  name?: string
  url?: string
  file_token?: string
}

/** 附件代理下载的基础路径：不同模块的通用飞书记录接口前缀不同。 */
export type FeishuAttachmentUrlBuilder = (
  entityCode: string,
  recordId: string,
  fileToken: string,
) => string

const DEFAULT_ATTACHMENT_URL_BUILDER: FeishuAttachmentUrlBuilder = (
  entityCode,
  recordId,
  fileToken,
) =>
  `/api/v1/quality/inspection/feishu/${encodeURIComponent(entityCode)}/records/${encodeURIComponent(recordId)}/attachments/${encodeURIComponent(fileToken)}/content`

export interface RenderFeishuValueOptions {
  /** 字段 ui_type，用于按类型格式化日期/勾选等原始值 */
  uiType?: string
  /** 附件代理下载地址构造器，默认走检验模块通用接口 */
  attachmentUrlBuilder?: FeishuAttachmentUrlBuilder
}

/** 通过后端代理下载飞书附件并以新标签页打开（附件 url 需带 token）。 */
async function openFeishuAttachment(
  entityCode: string | undefined,
  recordId: string,
  att: FeishuAttachment,
  message: FeishuMessage,
  attachmentUrlBuilder: FeishuAttachmentUrlBuilder,
): Promise<void> {
  if (!recordId || !att.file_token) {
    if (att.url) window.open(att.url, '_blank', 'noopener,noreferrer')
    return
  }
  try {
    const res = await fetch(
      attachmentUrlBuilder(entityCode ?? '', recordId, att.file_token),
    )
    if (!res.ok) {
      let msg = `下载失败(${res.status})`
      try {
        const errJson = await res.json()
        if (errJson?.message) msg = errJson.message
      } catch { /* 非 JSON 错误体则用默认文案 */ }
      throw new Error(msg)
    }
    const blob = await res.blob()
    const blobUrl = URL.createObjectURL(blob)
    window.open(blobUrl, '_blank')
  } catch (err) {
    message.error(err instanceof Error ? err.message : '附件下载失败')
  }
}

function formatDateTimeValue(value: unknown): string {
  // 飞书 DateTime 返回毫秒时间戳（可能为 number 或数字字符串）
  const numeric =
    typeof value === 'string' && /^\d+$/.test(value.trim())
      ? Number(value.trim())
      : (value as number)
  const parsed = dayjs(numeric)
  return parsed.isValid() ? parsed.format('YYYY-MM-DD') : String(value)
}

function formatCheckboxValue(value: unknown): string {
  if (value === true || value === 'True' || value === 'true') return '是'
  if (value === false || value === 'False' || value === 'false') return '否'
  return String(value)
}

/** 把飞书字段值渲染为可读内容：附件可点击、链接可点击、人员显示姓名、其余为文本。 */
export function renderFeishuValue(
  value: unknown,
  record: Record<string, unknown>,
  entityCode: string | undefined,
  message: FeishuMessage,
  options?: RenderFeishuValueOptions,
): ReactNode {
  const uiType = options?.uiType
  const attachmentUrlBuilder =
    options?.attachmentUrlBuilder ?? DEFAULT_ATTACHMENT_URL_BUILDER
  if (Array.isArray(value)) {
    if (value.length === 0) return '-'
    if (value.some((v) => (v as FeishuAttachment)?.url || (v as FeishuAttachment)?.file_token)) {
      return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {value.map((v, i) => {
            const att = v as FeishuAttachment
            return (
              <button
                key={i}
                type="button"
                style={{
                  padding: 0,
                  border: 'none',
                  background: 'transparent',
                  color: qualityTokens.primary,
                  textAlign: 'left',
                  cursor: 'pointer',
                  whiteSpace: 'normal',
                  wordBreak: 'break-all',
                  lineHeight: 1.4,
                  maxWidth: 220,
                }}
                onClick={() => void openFeishuAttachment(entityCode ?? '', String(record.record_id ?? ''), att, message, attachmentUrlBuilder)}
              >
                {att.name || '附件'}
              </button>
            )
          })}
        </div>
      )
    }
    if (value.some((v) => (v as { name?: string })?.name)) {
      const persons = (value as Array<{ name?: string; avatar_url?: string }>).filter(
        (v) => v && typeof v === 'object' && Boolean(v.name)
      )
      if (persons.length === 0) return '-'
      return (
        <Space size={4} wrap>
          {persons.map((p, i) => (
            <span key={i} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
              <Avatar size={20} src={p.avatar_url || undefined}>
                {p.name?.slice(0, 1) || '?'}
              </Avatar>
              <span>{p.name}</span>
            </span>
          ))}
        </Space>
      )
    }
    return (value as unknown[]).join('、')
  }
  if (typeof value === 'object' && value !== null) {
    const obj = value as { link?: string; text?: string; name?: string; avatar_url?: string }
    if (obj.name) {
      return (
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
          <Avatar size={20} src={obj.avatar_url || undefined}>
            {obj.name.slice(0, 1) || '?'}
          </Avatar>
          <span>{obj.name}</span>
        </span>
      )
    }
    if (obj.link) {
      return (
        <a href={obj.link} target="_blank" rel="noopener noreferrer">
          {obj.text || obj.link}
        </a>
      )
    }
  }
  if (value === null || value === undefined || value === '') return '-'
  if (uiType === 'DateTime' && (typeof value === 'number' || typeof value === 'string')) {
    return formatDateTimeValue(value)
  }
  if (uiType === 'Checkbox') {
    return formatCheckboxValue(value)
  }
  return String(value)
}
