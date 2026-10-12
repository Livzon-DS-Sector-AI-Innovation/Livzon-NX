"use client"

import { useMemo, useState, type ReactNode } from "react"
import ReactMarkdown from "react-markdown"

import {
  type AgentArtifact,
  AutomationArtifacts,
  collectAgentArtifacts,
} from "./AutomationArtifacts"

type BusinessTable = {
  headers: string[]
  rows: string[][]
}

type MessageSegment =
  | { type: "markdown"; content: string }
  | { type: "table"; table: BusinessTable }

const inlineMarkdownComponents = {
  p: ({ children }: { children?: ReactNode }) => <>{children}</>,
}

function splitTableRow(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, "").replace(/\|$/, "")
  return trimmed.split("|").map((cell) => cell.trim())
}

function isTableSeparator(line: string): boolean {
  const cells = splitTableRow(line)
  return (
    cells.length > 1 &&
    cells.every((cell) => /^:?-{3,}:?$/.test(cell.replace(/\s+/g, "")))
  )
}

function isTableRow(line: string): boolean {
  const trimmed = line.trim()
  return trimmed.includes("|") && splitTableRow(trimmed).length > 1
}

// Older stored replies can contain gateway diagnostics in their body.
// Hide only their labeled lines; keep ordinary business prose and tables.
function stripLegacyAgentDetails(content: string): string {
  let sourceContinuation = false
  return content.split(/\r?\n/).filter((line) => {
    const plain = line.trim().replace(/^[-*]\s+/, "").replace(/\*\*/g, "")
    if (/^(?:能力介绍\s+[a-z][\w-]*\s*[:：]|(?:任务|来源|查询条件|数据依据)\s*[:：])/.test(plain)) {
      sourceContinuation = plain.startsWith("来源")
      return false
    }
    if (sourceContinuation && /^(?:[a-f0-9]{32}|[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12})$/i.test(plain)) {
      return false
    }
    if (plain) sourceContinuation = false
    return true
  }).join("\n").replace(/\n{3,}/g, "\n\n").trim()
}

function parseBusinessSegments(content: string): MessageSegment[] {
  const lines = content.split(/\r?\n/)
  const segments: MessageSegment[] = []
  const markdownBuffer: string[] = []

  const flushMarkdown = () => {
    const markdown = markdownBuffer.join("\n").trim()
    if (markdown) {
      segments.push({ type: "markdown", content: markdown })
    }
    markdownBuffer.length = 0
  }

  let index = 0
  while (index < lines.length) {
    const line = lines[index]
    const nextLine = lines[index + 1]
    if (isTableRow(line) && nextLine && isTableSeparator(nextLine)) {
      flushMarkdown()
      const headers = splitTableRow(line)
      const rows: string[][] = []
      index += 2
      while (index < lines.length && isTableRow(lines[index])) {
        const row = splitTableRow(lines[index])
        rows.push(headers.map((_, cellIndex) => row[cellIndex] ?? ""))
        index += 1
      }
      if (headers.length && rows.length) {
        segments.push({ type: "table", table: { headers, rows } })
      }
      continue
    }
    markdownBuffer.push(line)
    index += 1
  }

  flushMarkdown()
  return segments.length ? segments : [{ type: "markdown", content }]
}

function isKeyValueTable(table: BusinessTable): boolean {
  if (table.headers.length !== 2) return false
  const [firstHeader, secondHeader] = table.headers.map((header) => header.trim())
  return (
    /字段|项目|名称|属性|类别/.test(firstHeader) ||
    /内容|说明|示例|值|明细/.test(secondHeader)
  )
}

function hasComplexDetail(value: string): boolean {
  return (
    value.length > 72 ||
    /\|\||\d+[.、]|；|;|，.*，/.test(value)
  )
}

function normalizeDetailMarkdown(value: string): string {
  const parts = value.split(/\s*\|\|\s*/).map((part) => part.trim()).filter(Boolean)
  if (parts.length > 1) {
    return parts.map((part) => `- ${part}`).join("\n")
  }
  return value
}

function previewText(value: string): string {
  const plain = value.replace(/\*\*/g, "").replace(/\s*\|\|\s*/g, " / ").trim()
  return plain.length > 54 ? `${plain.slice(0, 54)}...` : plain
}

function InlineMarkdown({ children }: { children: string }) {
  return (
    <ReactMarkdown components={inlineMarkdownComponents}>
      {children}
    </ReactMarkdown>
  )
}

function DetailValue({ value }: { value: string }) {
  if (!hasComplexDetail(value)) {
    return <InlineMarkdown>{value}</InlineMarkdown>
  }
  return (
    <details className="agent-business-details">
      <summary>
        <span>{previewText(value)}</span>
        <span className="agent-business-details-action">展开明细</span>
      </summary>
      <div className="agent-business-details-body">
        <ReactMarkdown>{normalizeDetailMarkdown(value)}</ReactMarkdown>
      </div>
    </details>
  )
}

function KeyValueBusinessCard({ table }: { table: BusinessTable }) {
  return (
    <section className="agent-business-panel" aria-label="业务卡片">
      <div className="agent-business-panel-head">
        <span>业务明细</span>
        <span>{table.rows.length} 项</span>
      </div>
      <div className="agent-business-kv-list">
        {table.rows.map((row, index) => {
          const label = row[0] || `项目 ${index + 1}`
          const value = row[1] || "-"
          return (
            <div className="agent-business-kv" key={`${label}-${index}`}>
              <div className="agent-business-label">{label}</div>
              <div className="agent-business-value">
                <DetailValue value={value} />
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}

function RecordBusinessCards({ table }: { table: BusinessTable }) {
  const [expanded, setExpanded] = useState(false)
  const isLarge = table.rows.length > 3
  const visibleRows = expanded || !isLarge ? table.rows : table.rows.slice(0, 3)
  const hiddenCount = table.rows.length - visibleRows.length

  return (
    <section className="agent-business-panel" aria-label="业务卡片列表">
      <div className="agent-business-panel-head">
        <span>查询结果</span>
        <span>
          共 {table.rows.length} 条{isLarge && !expanded ? "，已展示前 3 条" : ""}
        </span>
      </div>
      <div className="agent-business-card-list">
        {visibleRows.map((row, rowIndex) => {
          const title = row[0] || `记录 ${rowIndex + 1}`
          return (
            <article className="agent-business-card" key={`${title}-${rowIndex}`}>
              <div className="agent-business-card-title">{title}</div>
              <div className="agent-business-fields">
                {table.headers.slice(1).map((header, headerIndex) => {
                  const value = row[headerIndex + 1]
                  if (!value) return null
                  return (
                    <div className="agent-business-field" key={`${header}-${headerIndex}`}>
                      <span className="agent-business-label">{header}</span>
                      <span className="agent-business-value">
                        <DetailValue value={value} />
                      </span>
                    </div>
                  )
                })}
              </div>
            </article>
          )
        })}
      </div>
      {hiddenCount > 0 && (
        <button
          className="agent-business-more"
          type="button"
          onClick={() => setExpanded(true)}
        >
          查看更多 {hiddenCount} 条
        </button>
      )}
    </section>
  )
}

function BusinessCardsFromTable({ table }: { table: BusinessTable }) {
  if (isKeyValueTable(table)) {
    return <KeyValueBusinessCard table={table} />
  }
  return <RecordBusinessCards table={table} />
}

export function BusinessMessageContent({
  content,
  metadata,
  streaming = false,
  onArtifactAction,
}: {
  content: string
  metadata?: Record<string, unknown>
  streaming?: boolean
  onArtifactAction?: (artifact: AgentArtifact) => void
}) {
  const visibleContent = useMemo(() => stripLegacyAgentDetails(content), [content])
  const segments = useMemo(() => parseBusinessSegments(visibleContent), [visibleContent])
  const artifacts = useMemo(() => collectAgentArtifacts(metadata), [metadata])
  const hasContent = visibleContent.trim().length > 0

  return (
    <div className={`agent-markdown min-h-5 break-words${streaming ? " agent-markdown-streaming" : ""}`}>
      {hasContent ? (
        <>
          {segments.map((segment, index) =>
            segment.type === "table" ? (
              <BusinessCardsFromTable key={`table-${index}`} table={segment.table} />
            ) : (
              <ReactMarkdown key={`markdown-${index}`}>{segment.content}</ReactMarkdown>
            ),
          )}
          {streaming && <span className="agent-stream-cursor" aria-hidden="true" />}
          <AutomationArtifacts artifacts={artifacts} onAction={onArtifactAction} />
        </>
      ) : streaming && (
        <span className="agent-thinking-dots" aria-label="Livzon助手正在思考">
          <span />
          <span />
          <span />
        </span>
      )}
    </div>
  )
}
