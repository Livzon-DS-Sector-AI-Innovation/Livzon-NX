'use client'

import { useCallback, useState, useEffect, useRef } from 'react'
import { App, Table, Space, Input, Select, Button } from 'antd'
import { EditOutlined, DeleteOutlined, SearchOutlined, ToolOutlined, PlusOutlined, EyeOutlined, ImportOutlined } from '@ant-design/icons'
import { Equipment, EquipmentStatus } from '@/types/equipment'
import { useEquipmentStore } from '@/stores/equipment'
import { deleteEquipment } from '@/actions/equipment'
import { linkDanger, linkPrimary, linkWarning } from '@/components/equipment/shared-styles'
import { EquipmentDetailDrawer } from './EquipmentDetailDrawer'
import { EquipmentImportModal } from './EquipmentImportModal'

const statusOptions: { label: EquipmentStatus; value: EquipmentStatus }[] = (
  ['在用', '备用', '维修中', '停用', '报废'] as EquipmentStatus[]
).map(value => ({ label: value, value }))

// 待修正说明中的「【字段】」标记 → 表格列 dataIndex，
// 仅对问题字段所在单元格标红，而不是整行
const ISSUE_FIELD_MARKERS: Array<[string, string]> = [
  ['【设备编号】', 'equipment_no'],
  ['【设备名称】', 'name'],
  ['【规格型号】', 'model'],
  ['【生产厂家】', 'manufacturer'],
  ['【出厂日期】', 'production_date'],
  ['【出厂编号】', 'factory_no'],
  ['【入厂日期】', 'arrival_date'],
  ['【备注】', 'description'],
]

function issueFieldSet(note?: string | null): Set<string> {
  const fields = new Set<string>()
  if (!note) return fields
  for (const [marker, field] of ISSUE_FIELD_MARKERS) {
    if (note.includes(marker)) fields.add(field)
  }
  return fields
}

// 仅问题字段的单元格使用红色文字
const ISSUE_RED = '#c0392b'
const issueCellStyle = (
  note: string | null | undefined,
  field: string,
): React.CSSProperties | undefined =>
  issueFieldSet(note).has(field) ? { color: ISSUE_RED } : undefined

interface EquipmentTableProps {
  loading?: boolean
  onPageChange: (page: number, pageSize: number) => void
  /** 变化时重置分页到第一页 */
  resetKey: number
}


export function EquipmentTable({ loading = false, onPageChange, resetKey }: EquipmentTableProps) {
  const { message, modal } = App.useApp()
  const {
    equipments, total,
    statusFilter, keyword,
    departments, departmentFilter, setDepartmentFilter,
    setStatusFilter, setKeyword,
    openEquipmentDrawer, openRepairDrawer,
  } = useEquipmentStore()

  // 本地分页
  const [localPage, setLocalPage] = useState(1)
  const [localPageSize, setLocalPageSize] = useState(20)

  // resetKey 变化 → 重置到第一页
  useEffect(() => {
    setLocalPage(1)
  }, [resetKey])

  const [detailOpen, setDetailOpen] = useState(false)
  const [detailEquipment, setDetailEquipment] = useState<Equipment | null>(null)
  const [importOpen, setImportOpen] = useState(false)

  // 动态计算 scroll.y，使表头和筛选栏固定，仅表格数据行滚动
  const rootRef = useRef<HTMLDivElement>(null)
  const filterRef = useRef<HTMLDivElement>(null)
  const tableWrapRef = useRef<HTMLDivElement>(null)
  const [scrollY, setScrollY] = useState<number>(0)

  useEffect(() => {
    const tableWrap = tableWrapRef.current
    if (!tableWrap) return
    const observer = new ResizeObserver(() => {
      const h = tableWrap.clientHeight
      // 减去表头（small size 约 37px）和分页栏（约 56px）
      const y = h - 37 - 56
      setScrollY(y > 80 ? y : 80)
    })
    observer.observe(tableWrap)
    return () => observer.disconnect()
  }, [])


  const handleDelete = useCallback((record: Equipment) => {
    modal.confirm({
      title: '确认删除', content: `确定要删除设备 "${record.name}" 吗？`,
      okText: '确认', cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await deleteEquipment(record.id)
          message.success('删除设备成功')
          onPageChange(localPage, localPageSize)
        } catch (error) {
          message.error(error?.message || '删除设备失败')
        }
      },
    })
  }, [modal, message, onPageChange, localPage, localPageSize])

  // 技术参数 JSON 渲染为「参数名：值；…」文本
  const renderTechParams = (params: Record<string, unknown> | null | undefined) => {
    if (!params || Object.keys(params).length === 0) return '-'
    return Object.entries(params)
      .map(([key, value]) => `${key}：${String(value)}`)
      .join('；')
  }

  const columns = [
    {
      title: '序号', key: 'index', width: 60, fixed: 'start' as const,
      render: (_: unknown, __: Equipment, index: number) =>
        (localPage - 1) * localPageSize + index + 1,
    },
    {
      title: '设备编号', dataIndex: 'equipment_no', key: 'equipment_no', width: 140, fixed: 'start' as const,
      render: (v: string, record: Equipment) => (
        <span style={issueCellStyle(record.data_issue_note, 'equipment_no')}>{v}</span>
      ),
    },
    {
      title: '设备名称', dataIndex: 'name', key: 'name', width: 180, fixed: 'start' as const, ellipsis: true,
      render: (v: string, record: Equipment) => (
        <span style={issueCellStyle(record.data_issue_note, 'name')}>{v}</span>
      ),
    },
    {
      title: '规格型号', dataIndex: 'model', key: 'model', width: 150, ellipsis: true,
      render: (v: string | null, record: Equipment) => (
        <span style={issueCellStyle(record.data_issue_note, 'model')}>{v || '-'}</span>
      ),
    },
    {
      title: '技术参数', dataIndex: 'technical_params', key: 'technical_params', width: 220, ellipsis: true,
      render: (v: Record<string, unknown> | null | undefined) => renderTechParams(v),
    },
    {
      title: '生产厂家', dataIndex: 'manufacturer', key: 'manufacturer', width: 160, ellipsis: true,
      render: (v: string | null, record: Equipment) => (
        <span style={issueCellStyle(record.data_issue_note, 'manufacturer')}>{v || '-'}</span>
      ),
    },
    {
      title: '出厂日期', dataIndex: 'production_date', key: 'production_date', width: 110,
      render: (v: string | null, record: Equipment) => (
        <span style={issueCellStyle(record.data_issue_note, 'production_date')}>{v || '-'}</span>
      ),
    },
    {
      title: '出厂编号', dataIndex: 'factory_no', key: 'factory_no', width: 120,
      render: (v: string | null, record: Equipment) => (
        <span style={issueCellStyle(record.data_issue_note, 'factory_no')}>{v || '-'}</span>
      ),
    },
    {
      title: '入厂日期', dataIndex: 'arrival_date', key: 'arrival_date', width: 110,
      render: (v: string | null, record: Equipment) => (
        <span style={issueCellStyle(record.data_issue_note, 'arrival_date')}>{v || '-'}</span>
      ),
    },
    { title: '安装地点', dataIndex: 'location_name', key: 'location', width: 130, render: (n: string | null) => n || '-' },
    {
      title: '备注', dataIndex: 'description', key: 'description', width: 160, ellipsis: true,
      render: (v: string | null, record: Equipment) => (
        <span style={issueCellStyle(record.data_issue_note, 'description')}>{v || '-'}</span>
      ),
    },
    { title: '操作', key: 'action', width: 240, fixed: 'end' as const,
      render: (_: unknown, record: Equipment) => (
        <Space size={8}>
          <span role="button" onClick={() => { setDetailEquipment(record); setDetailOpen(true) }} style={linkPrimary}><EyeOutlined />详情</span>
          <span role="button" onClick={() => openRepairDrawer(record.id)} style={linkWarning}><ToolOutlined />报修</span>
          <span role="button" onClick={() => openEquipmentDrawer(record)} style={linkPrimary}><EditOutlined />编辑</span>
          <span role="button" onClick={() => handleDelete(record)} style={linkDanger}><DeleteOutlined />删除</span>
        </Space>
      ),
    },
  ]

  return (
    <div ref={rootRef} style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div ref={filterRef} style={{ marginBottom: 12, display: 'flex', gap: 12, alignItems: 'center', flexShrink: 0 }}>
        <Select placeholder="设备状态" allowClear style={{ width: 120 }}
          value={statusFilter || undefined} onChange={(v) => setStatusFilter(v || '')} options={statusOptions} />
        <Select
          placeholder="归属部门"
          allowClear
          style={{ width: 140 }}
          value={departmentFilter || undefined}
          onChange={(v) => setDepartmentFilter(v || null)}
          options={departments.map(d => ({ label: d.name, value: d.id }))}
        />
        <Input placeholder="搜索设备编号或名称" prefix={<SearchOutlined style={{ color: '#a4a097' }} />}
          style={{ width: 240 }} value={keyword} onChange={(e) => setKeyword(e.target.value)} allowClear />
        <div style={{ flex: 1 }} />
        <Button icon={<ImportOutlined />} onClick={() => setImportOpen(true)}>导入台账</Button>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => openEquipmentDrawer()}>新增设备</Button>
      </div>
      <div ref={tableWrapRef} style={{ flex: 1, minHeight: 0 }}>
        <Table
          columns={columns} dataSource={equipments} rowKey="id" size="small"
          loading={loading} scroll={{ x: 'max-content', y: scrollY || undefined }}
          onRow={(record) => ({
            title: record.data_issue_note || undefined,
          })}
          pagination={{
            current: localPage,
            pageSize: localPageSize,
            total: total,
            showSizeChanger: true,
            showQuickJumper: true,
            showTotal: (t) => `共 ${t} 条`,
            onChange: (p, ps) => {
              setLocalPage(p)
              if (ps !== localPageSize) setLocalPageSize(ps)
              onPageChange(p, ps)
            },
          }}
        />
      </div>
      <EquipmentDetailDrawer
        open={detailOpen} equipment={detailEquipment}
        categoryName={detailEquipment?.category_names || ''}
        locationName={detailEquipment?.location_name || ''}
        onClose={() => { setDetailOpen(false); setDetailEquipment(null) }}
      />
      <EquipmentImportModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImported={() => onPageChange(1, localPageSize)}
      />
    </div>
  )
}
