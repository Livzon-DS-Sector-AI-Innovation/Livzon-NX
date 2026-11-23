'use client'

import { useCallback, useState, useEffect } from 'react'
import { App, Table, Space, Input, Select, Button, Descriptions, Tag } from 'antd'
import { EditOutlined, SearchOutlined, ToolOutlined, PlusOutlined, ImportOutlined } from '@ant-design/icons'
import { Equipment, EquipmentStatus } from '@/types/equipment'
import { useEquipmentStore } from '@/stores/equipment'
import { linkPrimary, linkWarning } from '@/components/equipment/shared-styles'
import { EquipmentImportModal } from './EquipmentImportModal'

const statusOptions: { label: EquipmentStatus; value: EquipmentStatus }[] = (
  ['在用', '备用', '维修中', '停用', '报废'] as EquipmentStatus[]
).map(value => ({ label: value, value }))

const STATUS_TAG_COLOR: Record<string, string> = {
  '在用': 'green',
  '备用': 'blue',
  '维修中': 'orange',
  '停用': 'default',
  '报废': 'red',
}

interface EquipmentTableProps {
  loading?: boolean
  onPageChange: (page: number, pageSize: number) => void
  resetKey: number
  workshopCode?: string
}

// 技术参数 JSON 渲染为「参数名：值；…」
function renderTechParams(params: Record<string, unknown> | null | undefined) {
  if (!params || Object.keys(params).length === 0) return '-'
  return Object.entries(params).map(([k, v]) => `${k}：${String(v)}`).join('；')
}

export function EquipmentTable({ loading = false, onPageChange, resetKey, workshopCode }: EquipmentTableProps) {
  const { message } = App.useApp()
  const {
    equipments, total,
    statusFilter, keyword,
    departments, departmentFilter,
    categories, locations,
    selectedCategory, selectedLocation,
    setStatusFilter, setKeyword,
    setDepartmentFilter,
    setSelectedCategory, setSelectedLocation,
    openRepairDrawer,
    openEquipmentDrawer,
  } = useEquipmentStore()

  const [localPage, setLocalPage] = useState(1)
  const [localPageSize, setLocalPageSize] = useState(20)

  useEffect(() => { setLocalPage(1) }, [resetKey])

  const [importOpen, setImportOpen] = useState(false)

  // 展开行渲染：设备完整信息
  const expandedRowRender = (record: Equipment) => (
    <Descriptions
      size="small"
      column={{ xs: 1, sm: 2, lg: 4 }}
      items={[
        { key: 'manufacturer', label: '生产厂家', children: record.manufacturer || '-' },
        { key: 'production_date', label: '出厂日期', children: record.production_date || '-' },
        { key: 'factory_no', label: '出厂编号', children: record.factory_no || '-' },
        { key: 'arrival_date', label: '入厂日期', children: record.arrival_date || '-' },
        { key: 'tech', label: '技术参数', children: renderTechParams(record.technical_params), span: 2 },
        { key: 'remark', label: '备注', children: record.description || '-', span: 2 },
      ]}
    />
  )

  const columns = [
    { title: '设备编号', dataIndex: 'equipment_no', key: 'equipment_no', width: 140 },
    { title: '设备名称', dataIndex: 'name', key: 'name', width: 180, ellipsis: true },
    { title: '规格型号', dataIndex: 'model', key: 'model', width: 150, ellipsis: true, render: (v: string | null) => v || '-' },
    { title: '安装地点', dataIndex: 'location_name', key: 'location', width: 120, render: (v: string | null) => v || '-' },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: (v: string) => <Tag color={STATUS_TAG_COLOR[v] || 'default'}>{v}</Tag>,
    },
    {
      title: '操作', key: 'action', width: 180,
      render: (_: unknown, record: Equipment) => (
        <Space size={8}>
          <span role="button" style={linkWarning} onClick={() => openRepairDrawer(record.id)}>
            <ToolOutlined />报修
          </span>
          <span role="button" style={linkPrimary} onClick={() => openEquipmentDrawer(record)}>
            <EditOutlined />编辑
          </span>
        </Space>
      ),
    },
  ]

  // 分类选项（树转平）
  const categoryOptions = categories.map(c => ({ label: c.name, value: c.id }))
  const locationOptions = locations.map(l => ({ label: l.name, value: l.id }))

  return (
    <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* 筛选行 */}
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap', flexShrink: 0 }}>
        <Input
          placeholder="搜索设备编号或名称"
          prefix={<SearchOutlined style={{ color: '#a4a097' }} />}
          style={{ width: 220 }}
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          onPressEnter={() => onPageChange(1, localPageSize)}
          allowClear
        />
        <Select
          placeholder="状态" allowClear style={{ width: 100 }}
          value={statusFilter || undefined}
          onChange={(v) => setStatusFilter(v || '')}
          options={statusOptions}
        />
        <Select
          placeholder="分类" allowClear style={{ width: 130 }}
          value={selectedCategory || undefined}
          onChange={(v) => setSelectedCategory(v || null)}
          options={categoryOptions}
          showSearch optionFilterProp="label"
        />
        <Select
          placeholder="位置" allowClear style={{ width: 130 }}
          value={selectedLocation || undefined}
          onChange={(v) => setSelectedLocation(v || null)}
          options={locationOptions}
          showSearch optionFilterProp="label"
        />
        <Select
          placeholder="归属部门" allowClear style={{ width: 130 }}
          value={departmentFilter || undefined}
          onChange={(v) => setDepartmentFilter(v || null)}
          options={departments.map(d => ({ label: d.name, value: d.id }))}
        />
        <div style={{ flex: 1 }} />
        <Button icon={<ImportOutlined />} onClick={() => setImportOpen(true)}>导入</Button>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => openEquipmentDrawer()}>新增</Button>
      </div>

      {/* 表格 */}
      <div style={{ flex: 1, minHeight: 0 }}>
        <Table
          columns={columns}
          dataSource={equipments}
          rowKey="id"
          size="small"
          loading={loading}
          expandable={{ expandedRowRender }}
          pagination={{
            current: localPage,
            pageSize: localPageSize,
            total,
            showSizeChanger: true,
            showTotal: (t) => `共 ${t} 条`,
            onChange: (p, ps) => {
              setLocalPage(p)
              if (ps !== localPageSize) setLocalPageSize(ps)
              onPageChange(p, ps)
            },
          }}
        />
      </div>

      <EquipmentImportModal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        onImported={() => onPageChange(1, localPageSize)}
        workshopCode={workshopCode}
      />
    </div>
  )
}
