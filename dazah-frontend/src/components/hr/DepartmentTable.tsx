'use client'

import { useMemo } from 'react'
import { Table, Button, Input, Space, Popconfirm, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { SearchOutlined, ReloadOutlined, EditOutlined, DeleteOutlined, UserOutlined, ApartmentOutlined } from '@ant-design/icons'
import type { Department } from '@/types/hr'
import type { OrgTreeNode } from '@/types/hr'

interface DepartmentTableProps {
  departments: Department[]
  orgTreeData: OrgTreeNode[]
  loading: boolean
  pagination?: false | {
    current: number
    pageSize: number
    total: number
    onChange: (page: number, pageSize: number) => void
  }
  filters: { keyword: string; parentId: string | null; leaderName: string }
  onFilterChange: (filters: { keyword: string; parentId: string | null; leaderName: string }) => void
  onRowClick: (id: string) => void
  onEdit: (dept: Department) => void
  onDelete: (id: string) => void
  canEdit: boolean
  allDepartments: Department[]
}

interface TreeNode {
  title: string
  value: string
  children?: TreeNode[]
}

function buildDepartmentTree(departments: Department[]): TreeNode[] {
  const map = new Map<string, TreeNode>()
  const roots: TreeNode[] = []

  departments.forEach((dept) => {
    map.set(dept.id, { title: dept.name, value: dept.id, children: [] })
  })

  departments.forEach((dept) => {
    const node = map.get(dept.id)!
    if (dept.parent_id && map.has(dept.parent_id)) {
      map.get(dept.parent_id)!.children!.push(node)
    } else {
      roots.push(node)
    }
  })

  const cleanNode = (node: TreeNode): TreeNode => {
    if (!node.children || node.children.length === 0) {
      const { children: _children, ...rest } = node
      return rest
    }
    return { ...node, children: node.children.map(cleanNode) }
  }

  return roots.map(cleanNode)
}

export default function DepartmentTable({
  orgTreeData,
  loading,
  filters,
  onFilterChange,
  onRowClick,
  onEdit,
  onDelete,
  canEdit,
  allDepartments,
}: DepartmentTableProps) {
  const treeData = useMemo(() => buildDepartmentTree(allDepartments), [allDepartments])

  const columns: ColumnsType<OrgTreeNode> = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      width: 250,
      ellipsis: true,
      render: (name: string, record: OrgTreeNode) => (
        <Space>
          {record.type === 'employee' ? (
            <UserOutlined style={{ color: '#1677ff' }} />
          ) : (
            <ApartmentOutlined style={{ color: '#52c41a' }} />
          )}
          <span
            style={{ cursor: 'pointer', fontWeight: record.type === 'department' ? 500 : 400 }}
            onClick={() => record.type === 'department' && onRowClick(record.id)}
          >
            {name}
          </span>
        </Space>
      ),
    },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      width: 80,
      render: (type: string) => (
        <Tag color={type === 'department' ? 'blue' : 'default'}>
          {type === 'department' ? '部门' : '人员'}
        </Tag>
      ),
    },
    {
      title: '负责人/职位',
      dataIndex: 'leader_name',
      key: 'leader_name',
      width: 120,
      render: (v: string | null | undefined) => v || '-',
    },
    {
      title: '编制人数',
      dataIndex: 'headcount',
      key: 'headcount',
      width: 90,
      render: (v: number | null | undefined) => v ?? '-',
    },
    {
      title: '在职人数',
      dataIndex: 'current_count',
      key: 'current_count',
      width: 90,
      render: (v: number | null | undefined) => v ?? '-',
    },
    {
      title: '空编数',
      dataIndex: 'vacancy',
      key: 'vacancy',
      width: 80,
      render: (vacancy: number | null | undefined) => {
        if (vacancy === undefined || vacancy === null) return '-'
        return (
          <span style={{ color: vacancy > 0 ? '#ff4d4f' : undefined, fontWeight: vacancy > 0 ? 500 : undefined }}>
            {vacancy}
          </span>
        )
      },
    },
  ]

  if (canEdit) {
    columns.push({
      title: '操作',
      key: 'action',
      width: 120,
      fixed: 'right' as const,
      render: (_: unknown, record: OrgTreeNode) =>
        record.type === 'department' ? (
          <Space size="small">
            <Button
              type="text"
              size="small"
              icon={<EditOutlined />}
              onClick={(e) => {
                e.stopPropagation()
                const dept = allDepartments.find(d => d.id === record.id)
                if (dept) onEdit(dept)
              }}
            >
              编辑
            </Button>
            <Popconfirm
              title="确认删除"
              description={`确定要删除 ${record.name} 吗？`}
              onConfirm={(e) => {
                e?.stopPropagation()
                onDelete(record.id)
              }}
              onCancel={(e) => e?.stopPropagation()}
              okText="确定"
              cancelText="取消"
            >
              <Button
                type="text"
                size="small"
                danger
                icon={<DeleteOutlined />}
                onClick={(e) => e.stopPropagation()}
              >
                删除
              </Button>
            </Popconfirm>
          </Space>
        ) : <></>,
    })
  }

  const handleSearch = () => {
    onFilterChange({ ...filters })
  }

  const handleReset = () => {
    onFilterChange({ keyword: '', parentId: null, leaderName: '' })
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-nowrap gap-2 items-center">
        <Input
          placeholder="搜索部门名称"
          value={filters.keyword}
          onChange={(e) => onFilterChange({ ...filters, keyword: e.target.value })}
          prefix={<SearchOutlined />}
          style={{ width: 180 }}
          allowClear
          onPressEnter={handleSearch}
        />
        <Input
          placeholder="负责人"
          value={filters.leaderName}
          onChange={(e) => onFilterChange({ ...filters, leaderName: e.target.value })}
          style={{ width: 120 }}
          allowClear
          onPressEnter={handleSearch}
        />
        <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>
          搜索
        </Button>
        <Button icon={<ReloadOutlined />} onClick={handleReset}>
          重置
        </Button>
      </div>

      <Table
        columns={columns}
        dataSource={orgTreeData}
        rowKey="id"
        loading={loading}
        pagination={false}
        scroll={{ x: 1000, y: 600 }}
        size="small"
        expandable={{
          childrenColumnName: 'children',
          defaultExpandAllRows: false,
          expandRowByClick: false,
        }}
        onRow={(record) => ({
          onClick: () => record.type === 'department' && onRowClick(record.id),
          style: { cursor: record.type === 'department' ? 'pointer' : 'default' },
        })}
      />
    </div>
  )
}
