'use client'

import { useEffect, useMemo, useState } from 'react'
import { Modal, Select, Input, Space, Table, Tag } from 'antd'
import { fetchDocumentDepartments, fetchDocumentEntries } from '@/lib/api/client/quality'
import type { DocumentDepartmentItem, DocumentEntryItem } from '@/types/quality'

export interface DocumentCatalogPick {
  name: string
  code: string | null
  /** 文件管理条目 ID：培训勾选时锁定，后续 AI 出题按此 ID 精确读取内容 */
  entryId: string
}

interface Props {
  open: boolean
  onClose: () => void
  onConfirm: (items: DocumentCatalogPick[]) => void
  /** 已培训/已勾选的文件名称（归一化后匹配），置灰不可再选 */
  excludeNames?: string[]
}

const PAGE_SIZE = 20

/**
 * 从质量管理-文件管理选择培训内容：
 * 下拉先选部门 → 勾选该部门文件条目 → 可继续切换其他部门累积勾选 → 确认后带回《名称》（编码）。
 */
export default function DocumentCatalogPickerModal({ open, onClose, onConfirm, excludeNames = [] }: Props) {
  const [departments, setDepartments] = useState<DocumentDepartmentItem[]>([])
  const [deptId, setDeptId] = useState('')
  const [keyword, setKeyword] = useState('')
  const [items, setItems] = useState<DocumentEntryItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState<Map<string, DocumentCatalogPick>>(new Map())

  const excludeSet = useMemo(
    () => new Set(excludeNames.map((n) => (n || '').replace(/\s+/g, ''))),
    [excludeNames],
  )

  useEffect(() => {
    if (!open) return
    fetchDocumentDepartments()
      .then((d) => {
        setDepartments(d)
        setDeptId((prev) => prev || (d[0]?.id ?? ''))
      })
      .catch(() => setDepartments([]))
  }, [open])

  useEffect(() => {
    if (!open || !deptId) return
    let cancelled = false
    // 依赖变化时同步进入加载态：仅筛选条件变化触发
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true)
    fetchDocumentEntries({
      department_id: deptId,
      keyword: keyword || undefined,
      page,
      page_size: PAGE_SIZE,
    })
      .then((res) => {
        if (cancelled) return
        setItems(res.items)
        setTotal(res.total)
      })
      .catch(() => {
        if (!cancelled) {
          setItems([])
          setTotal(0)
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, deptId, keyword, page])

  const confirm = () => {
    onConfirm(Array.from(selected.values()))
    setSelected(new Map())
    setKeyword('')
    setPage(1)
  }

  return (
    <Modal
      open={open}
      title="从文件管理选择培训内容（勾选的文件将录入培训内容）"
      width={880}
      onCancel={onClose}
      onOk={confirm}
      okText={`确认录入（已选 ${selected.size} 条）`}
      cancelText="取消"
      okButtonProps={{ disabled: selected.size === 0 }}
      destroyOnHidden
    >
      <Space size={8} wrap style={{ marginBottom: 12 }}>
        <span>部门：</span>
        <Select
          style={{ width: 220 }}
          placeholder="选择部门"
          value={deptId || undefined}
          onChange={(v) => {
            setDeptId(v)
            setPage(1)
          }}
          options={departments.map((d) => ({ value: d.id, label: d.name }))}
          showSearch
          optionFilterProp="label"
        />
        <Input.Search
          style={{ width: 240 }}
          placeholder="搜索文件名称/编码"
          allowClear
          onSearch={(v) => {
            setKeyword(v.trim())
            setPage(1)
          }}
        />
      </Space>
      <Table
        size="small"
        loading={loading}
        rowKey="id"
        dataSource={items}
        columns={[
          { title: '编码', dataIndex: 'code', width: 180, ellipsis: true },
          { title: '文件名称', dataIndex: 'name', ellipsis: true },
          { title: '生效日期', dataIndex: 'effective_date', width: 100 },
        ]}
        rowSelection={{
          selectedRowKeys: items.filter((i) => selected.has(i.id)).map((i) => i.id),
          preserveSelectedRowKeys: true,
          onChange: (_keys, rows) => {
            setSelected((prev) => {
              const next = new Map(prev)
              items.forEach((i) => next.delete(i.id))
              rows.forEach((r) => next.set(r.id, { name: r.name, code: r.code, entryId: r.id }))
              return next
            })
          },
          getCheckboxProps: (r: DocumentEntryItem) => ({
            disabled: excludeSet.has((r.name || '').replace(/\s+/g, '')),
          }),
        }}
        pagination={{
          current: page,
          pageSize: PAGE_SIZE,
          total,
          showSizeChanger: false,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p) => setPage(p),
        }}
      />
      {selected.size > 0 && (
        <div style={{ marginTop: 8 }}>
          <span style={{ marginRight: 8 }}>已选 {selected.size} 条：</span>
          {Array.from(selected.values()).map((s) => (
            <Tag
              key={s.name}
              closable
              onClose={() =>
                setSelected((prev) => {
                  const next = new Map(prev)
                  next.delete(s.name)
                  return next
                })
              }
            >
              {s.name}
            </Tag>
          ))}
        </div>
      )}
    </Modal>
  )
}
