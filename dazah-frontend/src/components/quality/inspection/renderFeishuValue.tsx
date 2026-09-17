import type { ReactNode } from 'react'
import { useEffect, useRef, useState } from 'react'
import { qualityTokens } from '../themeTokens'
import { Avatar, Image, Space, Tag } from 'antd'
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

export interface FeishuAttachmentPreviewContext {
  record: Record<string, unknown>
  attachment: FeishuAttachment
  entityCode?: string
}

export interface RenderFeishuValueOptions {
  /** 字段 ui_type，用于按类型格式化日期/勾选等原始值 */
  uiType?: string
  /** 公式字段的结果类型：公式返回日期时飞书回读为 Excel 序列号，需换算展示 */
  resultUiType?: string
  /** 字段名，用于对「结果判断」等结论类字段做语义着色 */
  fieldName?: string
  /** 附件代理下载地址构造器，默认走检验模块通用接口 */
  attachmentUrlBuilder?: FeishuAttachmentUrlBuilder
  /** 提供时非图片附件点击进入弹窗预览；不提供则保持下载行为 */
  onAttachmentPreview?: (context: FeishuAttachmentPreviewContext) => void
}

/** 字段渲染所需的类型信息（来自实体字段元数据接口） */
export interface FeishuFieldTypeInfo {
  uiType?: string
  resultUiType?: string
}

/** 字段名 -> 类型信息，供表格列与详情抽屉按类型渲染 */
export type FeishuFieldTypeMap = Record<string, FeishuFieldTypeInfo | undefined>

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

/** 公式字段返回日期时的取值换算。
 *
 * 飞书多维表格里公式日期列（如「校验有效期」= 日期列 + 365 天）回读的是
 * Excel 日期序列号（1899-12-30 起的天数，如 46406 = 2027-01-19），而不是
 * 毫秒时间戳；引用日期字段的公式也可能直接给毫秒时间戳，两种都兼容。
 */
function formatFormulaDateValue(value: unknown): string {
  const numeric =
    typeof value === 'string' && /^\d+(\.\d+)?$/.test(value.trim())
      ? Number(value.trim())
      : (value as number)
  if (!Number.isFinite(numeric)) return String(value)
  if (numeric > 1e11) return formatDateTimeValue(numeric)
  if (numeric <= 0 || numeric > 400000) return String(value)
  return dayjs('1899-12-30').add(Math.round(numeric), 'day').format('YYYY-MM-DD')
}

const DATE_LIKE_UI_TYPES = ['DateTime', 'CreatedTime', 'ModifiedTime']

/** 列名带日期语义的公式/查找列：元数据缺 result_ui_type 时按列名兜底换算日期。 */
const FORMULA_DATE_NAME_PATTERN = /日期|有效期|时间/

function formatCheckboxValue(value: unknown): string {
  if (value === true || value === 'True' || value === 'true') return '是'
  if (value === false || value === 'False' || value === 'false') return '否'
  return String(value)
}

const IMAGE_EXTENSIONS = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg']

function isImageAttachment(att: FeishuAttachment): boolean {
  const ext = (att.name || '').split('.').pop()?.toLowerCase() || ''
  return IMAGE_EXTENSIONS.includes(ext)
}

/** 附件代理 content URL → 缩略图 URL（content 后缀可能带 query，如 ?year=）。 */
function toThumbnailUrl(contentUrl: string): string {
  return contentUrl.replace(/\/content(\?|$)/, '/thumbnail$1')
}

/** 图片附件内联缩略图：进入视口后才从缩略图端点拉小图（避免原图全量字节），
 * 点击放大时加载原图（后端缓存命中秒开）；失败回退为下载按钮。 */
function AttachmentImage({
  entityCode,
  recordId,
  attachment,
  attachmentUrlBuilder,
  message,
}: {
  entityCode: string
  recordId: string
  attachment: FeishuAttachment
  attachmentUrlBuilder: FeishuAttachmentUrlBuilder
  message: FeishuMessage
}) {
  const [src, setSrc] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  const [inView, setInView] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  // builder 引用每次 render 可能变化（闭包），用 ref 避免 effect 重复触发
  const buildersRef = useRef({ attachmentUrlBuilder, message })
  useEffect(() => {
    buildersRef.current = { attachmentUrlBuilder, message }
  })

  useEffect(() => {
    const node = containerRef.current
    if (!node || typeof IntersectionObserver === 'undefined') {
      setInView(true)
      return
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setInView(true)
          observer.disconnect()
        }
      },
      { rootMargin: '120px' },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  const fileToken = attachment.file_token
  const ext = (attachment.name || '').split('.').pop()?.toLowerCase() || ''
  const isSvg = ext === 'svg'

  useEffect(() => {
    let cancelled = false
    let objectUrl: string | null = null
    // 附件 token 变化时重置图片加载状态（effect 内重置是这里的惯用模式）
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setFailed(false)
    setSrc(null)
    if (!inView) return
    if (!fileToken || !recordId) {
      if (attachment.url) setSrc(attachment.url)
      return
    }
    const { attachmentUrlBuilder: builder } = buildersRef.current
    const contentUrl = builder(entityCode, recordId, fileToken)
    ;(async () => {
      try {
        // SVG 后端 PIL 不处理，直接走原图代理；其余走缩略图端点
        const targetUrl = isSvg ? contentUrl : toThumbnailUrl(contentUrl)
        const res = await fetch(targetUrl)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const blob = await res.blob()
        if (cancelled) return
        objectUrl = URL.createObjectURL(blob)
        setSrc(objectUrl)
      } catch {
        if (!cancelled) setFailed(true)
      }
    })()
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [inView, fileToken, attachment.url, entityCode, recordId, isSvg])

  if (failed) {
    return (
      <button
        type="button"
        style={{
          padding: 0,
          border: 'none',
          background: 'transparent',
          color: qualityTokens.primary,
          textAlign: 'left',
          cursor: 'pointer',
        }}
        onClick={() => void openFeishuAttachment(entityCode, recordId, attachment, buildersRef.current.message, attachmentUrlBuilder)}
      >
        {attachment.name || '附件'}
      </button>
    )
  }

  if (!inView || !src) {
    return (
      <div
        ref={containerRef}
        style={{
          width: 120,
          height: 80,
          background: 'rgba(0, 0, 0, 0.04)',
          borderRadius: 4,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: 12,
          color: 'rgba(0, 0, 0, 0.35)',
        }}
      >
        图片加载中…
      </div>
    )
  }

  const originalUrl =
    fileToken && recordId
      ? attachmentUrlBuilder(entityCode, recordId, fileToken)
      : src

  return (
    <div ref={containerRef}>
      <Image
        src={src}
        alt={attachment.name || '附件'}
        loading="lazy"
        style={{ maxWidth: 200, maxHeight: 200, objectFit: 'cover', borderRadius: 4 }}
        preview={{ src: originalUrl, mask: '点击查看' }}
      />
    </div>
  )
}

/** 把飞书字段值渲染为可读内容：附件可点击、链接可点击、人员显示姓名、
 * 「结果判断」按语义着色（fieldName 传入时）、其余为文本。 */
export function renderFeishuValue(
  value: unknown,
  record: Record<string, unknown>,
  entityCode: string | undefined,
  message: FeishuMessage,
  options?: RenderFeishuValueOptions,
): ReactNode {
  const uiType = options?.uiType
  const fieldName = options?.fieldName
  const attachmentUrlBuilder =
    options?.attachmentUrlBuilder ?? DEFAULT_ATTACHMENT_URL_BUILDER
  if (Array.isArray(value)) {
    if (value.length === 0) return '-'
    if (value.some((v) => (v as FeishuAttachment)?.url || (v as FeishuAttachment)?.file_token)) {
      return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {value.map((v, i) => {
            const att = v as FeishuAttachment
            // 图片附件直接内联预览（点击放大），非图片走下载链接
            if (isImageAttachment(att)) {
              return (
                <AttachmentImage
                  key={i}
                  entityCode={entityCode ?? ''}
                  recordId={String(record.record_id ?? '')}
                  attachment={att}
                  attachmentUrlBuilder={attachmentUrlBuilder}
                  message={message}
                />
              )
            }
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
                onClick={() => {
                  if (options?.onAttachmentPreview) {
                    options.onAttachmentPreview({
                      record,
                      attachment: att,
                      entityCode: entityCode ?? undefined,
                    })
                    return
                  }
                  void openFeishuAttachment(entityCode ?? '', String(record.record_id ?? ''), att, message, attachmentUrlBuilder)
                }}
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
  if (
    options?.resultUiType &&
    DATE_LIKE_UI_TYPES.includes(options.resultUiType) &&
    (typeof value === 'number' || typeof value === 'string')
  ) {
    return formatFormulaDateValue(value)
  }
  if (
    (uiType === 'Formula' || uiType === 'Lookup') &&
    fieldName &&
    FORMULA_DATE_NAME_PATTERN.test(fieldName) &&
    (typeof value === 'number' ||
      (typeof value === 'string' && /^\d+(\.\d+)?$/.test(value.trim())))
  ) {
    // 部分飞书 Base 的公式列（如「下次检定日期」= EDATE(检定日期, 周期)-1）
    // 元数据不带结果类型，回读值为 Excel 序列号或毫秒时间戳字符串，按列名兜底换算
    return formatFormulaDateValue(value)
  }
  if (
    (uiType === 'DateTime' || uiType === 'CreatedTime' || uiType === 'ModifiedTime') &&
    (typeof value === 'number' || typeof value === 'string')
  ) {
    return formatDateTimeValue(value)
  }
  if (uiType === 'Checkbox') {
    return formatCheckboxValue(value)
  }
  // 「结果判断」为检验结论语义字段：合格/不合格着色展示（固体/液体等物料检验表）
  if (
    fieldName === '结果判断' &&
    (value === '合格' || value === '不合格' || value === '待判定')
  ) {
    const color = value === '合格' ? 'success' : value === '不合格' ? 'error' : 'default'
    return <Tag color={color}>{value}</Tag>
  }
  return String(value)
}
