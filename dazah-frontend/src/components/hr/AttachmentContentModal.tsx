'use client'

import { useEffect, useMemo, useState } from 'react'
import { Modal, Checkbox, Spin, Tag } from 'antd'
import type { PlanAttachmentSection } from '@/types/hr'
import { fetchSectionPreview } from '@/lib/api/client/hr'

/** 附件内可勾选的培训文件条目 */
export interface ContentEntry {
  key: string
  group: string
  name: string
  code: string | null
  attachment_id: string
}

const norm = (s: string) => (s || '').replace(/\s+/g, '')

/** 从附件预览（docx 表格块 / xlsx sheets）解析"文件名称+编号"清单 */
function parsePreview(attachmentId: string, fileName: string, preview: any): ContentEntry[] {
  const tables: { title: string; header: string[]; rows: string[][] }[] = []
  if (preview?.kind === 'tables') {
    ;(preview.tables || []).forEach((t: any) =>
      tables.push({ title: t.title || fileName, header: t.header || [], rows: t.rows || [] }),
    )
  } else if (preview?.kind === 'table') {
    // 单 sheet / 整文件表格：header/rows 在顶层（如 xlsx_sheet 预览）
    tables.push({
      title: preview.title || fileName,
      header: preview.header || [],
      rows: preview.rows || [],
    })
  } else {
    ;(preview?.blocks || []).forEach((b: any) => {
      if (b?.type === 'table' && Array.isArray(b.rows) && b.rows.length) {
        tables.push({ title: fileName, header: b.rows[0] || [], rows: b.rows.slice(1) })
      }
    })
  }
  const entries: ContentEntry[] = []
  for (const t of tables) {
    const header = t.header || []
    let nameIdx = header.findIndex((h) => norm(h).includes('名称'))
    if (nameIdx < 0) nameIdx = 1
    const codeIdx = header.findIndex((h) => norm(h).includes('编码') || norm(h).includes('编号'))
    for (const row of t.rows) {
      const name = norm(row?.[nameIdx] ?? '')
      if (!name || name.startsWith('备注') || /^\d+$/.test(name)) continue
      const code = codeIdx >= 0 ? norm(row?.[codeIdx] ?? '') || null : null
      entries.push({ key: `${attachmentId}|${name}`, group: t.title, name, code, attachment_id: attachmentId })
    }
  }
  return entries
}

interface Props {
  open: boolean
  sections: PlanAttachmentSection[]
  usedNames: Set<string>
  initialCheckedKeys: string[]
  onClose: () => void
  onConfirm: (entries: ContentEntry[]) => void
}

/** 选择培训附件内容：勾选附件条目内的文件清单，录入签到表培训内容 */
export default function AttachmentContentModal({
  open,
  sections,
  usedNames,
  initialCheckedKeys,
  onClose,
  onConfirm,
}: Props) {
  const [loading, setLoading] = useState(false)
  const [entries, setEntries] = useState<ContentEntry[]>([])
  const [checked, setChecked] = useState<string[]>([])

  useEffect(() => {
    if (!open) return
    let cancelled = false
    queueMicrotask(() => {
      if (cancelled) return
      setChecked(initialCheckedKeys)
      setLoading(true)
    })
    Promise.all(
      sections.map(async (s) => {
        try {
          const res = await fetchSectionPreview(s.id)
          // 分组标题：附件编号 + 条目标题（如「附件2 - 毒酚酸培训附件」）
          const groupLabel = s.annex_no ? `${s.annex_no}${s.title ? ' - ' + s.title : ''}` : (s.title || s.id)
          return parsePreview(s.id, groupLabel, res.data)
        } catch {
          return [] as ContentEntry[]
        }
      }),
    ).then((lists) => {
      if (cancelled) return
      setEntries(lists.flat())
      setLoading(false)
    })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, sections])

  const groups = useMemo(() => {
    const map = new Map<string, ContentEntry[]>()
    entries.forEach((e) => {
      const list = map.get(e.group) || []
      list.push(e)
      map.set(e.group, list)
    })
    return Array.from(map.entries())
  }, [entries])

  return (
    <Modal
      open={open}
      title="选择培训附件内容（勾选的文件将录入培训内容）"
      width={780}
      onCancel={onClose}
      onOk={() => onConfirm(entries.filter((e) => checked.includes(e.key)))}
      okText="确认录入"
      cancelText="取消"
      destroyOnHidden
    >
      {loading ? (
        <div className="py-8 text-center">
          <Spin />
        </div>
      ) : groups.length === 0 ? (
        <div className="text-gray-400 py-8 text-center">附件未解析出可选的文件清单内容</div>
      ) : (
        <div style={{ maxHeight: 480, overflow: 'auto' }}>
          {groups.map(([title, list]) => (
            <div key={title} className="mb-4">
              <div className="font-semibold mb-1 text-gray-700">{title}</div>
              <Checkbox.Group value={checked} onChange={(v) => setChecked(v as string[])}>
                <div className="flex flex-col gap-1">
                  {list.map((e) => {
                    const used = usedNames.has(e.name)
                    return (
                      <Checkbox key={e.key} value={e.key} disabled={used}>
                        <span className={used ? 'text-gray-400' : undefined}>
                          {e.name}
                          {e.code && <span className="text-gray-500">（{e.code}）</span>}
                          {used && <Tag style={{ marginLeft: 6 }}>已培训</Tag>}
                        </span>
                      </Checkbox>
                    )
                  })}
                </div>
              </Checkbox.Group>
            </div>
          ))}
        </div>
      )}
    </Modal>
  )
}
