import type { ReactNode } from 'react'
import { qualityTokens } from '../themeTokens'
import { Avatar, Space } from 'antd'
import type { App } from 'antd'

type FeishuMessage = ReturnType<typeof App.useApp>['message']

export interface FeishuAttachment {
  name?: string
  url?: string
  file_token?: string
}

/** 通过后端代理下载飞书附件并以新标签页打开（附件 url 需带 token）。 */
async function openFeishuAttachment(
  entityCode: string,
  recordId: string,
  att: FeishuAttachment,
  message: FeishuMessage
): Promise<void> {
  if (!entityCode || !recordId || !att.file_token) {
    if (att.url) window.open(att.url, '_blank', 'noopener,noreferrer')
    return
  }
  try {
    const res = await fetch(
      `/api/v1/quality/inspection/feishu/${encodeURIComponent(entityCode)}/records/${encodeURIComponent(recordId)}/attachments/${encodeURIComponent(att.file_token)}/content`
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

/** 把飞书字段值渲染为可读内容：附件可点击、链接可点击、人员显示姓名、其余为文本。 */
export function renderFeishuValue(
  value: unknown,
  record: Record<string, unknown>,
  entityCode: string | undefined,
  message: FeishuMessage
): ReactNode {
  if (Array.isArray(value)) {
    if (value.length === 0) return '-'
    if (value.some((v) => (v as { url?: string })?.url)) {
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
                onClick={() => void openFeishuAttachment(entityCode ?? '', String(record.record_id ?? ''), att, message)}
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
  return String(value)
}
