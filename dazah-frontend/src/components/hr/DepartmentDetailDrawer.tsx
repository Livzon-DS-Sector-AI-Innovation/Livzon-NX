'use client'

import { Drawer, Descriptions, Tag, Button, Space, Divider, Flex, Typography, Badge, Popconfirm } from 'antd'
import { ApartmentOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons'
import { Department } from '@/types/hr'

const { Text } = Typography

interface DepartmentDetailDrawerProps {
  open: boolean
  department: Department | null
  canEdit: boolean
  onClose: () => void
  onEdit: (dept: Department) => void
  onDelete: (id: string) => void
  onChildClick: (id: string) => void
  allDepartments?: Department[]
}

export default function DepartmentDetailDrawer({
  open,
  department,
  canEdit,
  onClose,
  onEdit,
  onDelete,
  onChildClick,
  allDepartments = [],
}: DepartmentDetailDrawerProps) {
  if (!department) {
    return (
      <Drawer title="部门详情" open={open} onClose={onClose} size="large" placement="right">
        <div style={{ textAlign: 'center', color: '#999', paddingTop: 80 }}>
          暂无部门数据
        </div>
      </Drawer>
    )
  }

  // 查找上级部门名称
  const parentName = department.parent_id
    ? allDepartments.find(d => d.id === department.parent_id)?.name || '-'
    : '-'

  const footer = canEdit ? (
    <Space>
      <Button type="primary" icon={<EditOutlined />} onClick={() => onEdit(department)}>
        编辑部门
      </Button>
      <Popconfirm
        title="确定要删除该部门吗？"
        description="删除后不可恢复，请谨慎操作。"
        onConfirm={() => onDelete(department.id)}
        okText="确定"
        cancelText="取消"
      >
        <Button danger icon={<DeleteOutlined />}>删除部门</Button>
      </Popconfirm>
    </Space>
  ) : null

  return (
    <Drawer
      title={
        <Space>
          <ApartmentOutlined />
          <span>部门详情</span>
        </Space>
      }
      open={open}
      onClose={onClose}
      size="large"
      placement="right"
      footer={footer}
    >
      {/* 基本信息 - 与编辑表单字段一致 */}
      <Descriptions
        column={1}
        size="small"
        styles={{ label: { width: 80, color: '#666' }, content: { fontWeight: 500 } }}
        title="基本信息"
      >
        <Descriptions.Item label="部门名称">{department.name}</Descriptions.Item>
        <Descriptions.Item label="负责人">{department.leader_name || '-'}</Descriptions.Item>
        <Descriptions.Item label="上级部门">{parentName}</Descriptions.Item>
        <Descriptions.Item label="编制人数">{department.headcount ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="在职人数">{department.current_count ?? '-'}</Descriptions.Item>
        <Descriptions.Item label="空编数">
          {department.vacancy != null ? (
            <Tag color={department.vacancy > 0 ? 'red' : 'green'}>{department.vacancy}</Tag>
          ) : '-'}
        </Descriptions.Item>
        <Descriptions.Item label="排序顺序">{department.sort_order ?? '-'}</Descriptions.Item>
      </Descriptions>

      {/* 部门描述 */}
      <Divider style={{ margin: '16px 0' }} />
      <div>
        <Text strong style={{ fontSize: 14, marginBottom: 8, display: 'block' }}>
          部门描述
        </Text>
        <div style={{ color: '#666', lineHeight: 1.8 }}>
          {department.description || '暂无描述'}
        </div>
      </div>

      {/* 下级部门 */}
      <Divider style={{ margin: '16px 0' }} />
      <div>
        <Text strong style={{ fontSize: 14, marginBottom: 8, display: 'block' }}>
          下级部门
        </Text>
        {department.children && department.children.length > 0 ? (
          <Flex vertical gap={4}>
            {department.children.map((child) => (
              <Flex
                key={child.id}
                justify="space-between"
                align="center"
                style={{ padding: '4px 0' }}
              >
                <Button
                  type="link"
                  style={{ padding: 0, height: 'auto' }}
                  onClick={() => onChildClick(child.id)}
                >
                  <ApartmentOutlined style={{ marginRight: 6 }} />
                  {child.name}
                </Button>
                <Badge
                  count={child.current_count ?? 0}
                  showZero
                  style={{ backgroundColor: '#1677ff' }}
                />
              </Flex>
            ))}
          </Flex>
        ) : (
          <div style={{ color: '#999', fontSize: 13, padding: '12px 0' }}>
            暂无下级部门
          </div>
        )}
      </div>
    </Drawer>
  )
}
