'use client'

import { useState } from 'react'
import { App, Table, Button, Space, Popconfirm, Tooltip } from 'antd'
import { EditOutlined, DeleteOutlined, EyeOutlined } from '@ant-design/icons'
import { Employee } from '@/types/hr'
import { deleteEmployee } from '@/actions/hr'

interface EmployeeTableProps {
  employees: Employee[]
  total: number
  page: number
  pageSize: number
  onPageChange: (page: number, pageSize: number) => void
  onRefresh: () => void
  onEdit: (employee: Employee) => void
  onView: (employee: Employee) => void
}

export default function EmployeeTable({
  employees,
  total,
  page,
  pageSize,
  onPageChange,
  onRefresh,
  onEdit,
  onView }: EmployeeTableProps) {
  const { message } = App.useApp()
  const [loading, setLoading] = useState(false)

  const handleDelete = async (id: string) => {
    setLoading(true)
    try {
      const result = await deleteEmployee(id)
      const syncStatus = result.meta?.feishu_sync_status
      if (syncStatus === 'success') {
        message.success('删除成功，已同步到飞书')
      } else if (syncStatus?.startsWith('failed')) {
        message.warning(`删除成功，但飞书同步失败：${syncStatus.replace('failed: ', '')}`)
      } else {
        message.success('删除成功')
      }
      onRefresh()
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '删除失败')
    } finally {
      setLoading(false)
    }
  }

  // 10个核心列
  const columns = [
    {
      title: '工号',
      dataIndex: 'employee_number',
      key: 'employee_number',
      width: 110,
      fixed: 'left' as const },
    {
      title: '姓名',
      dataIndex: 'name',
      key: 'name',
      width: 90,
      fixed: 'left' as const,
      render: (text: string, record: Employee) => (
        <a onClick={() => onView(record)} className="text-blue-600 hover:text-blue-800 cursor-pointer">
          {text}
        </a>
      ) },
    {
      title: '域账户',
      dataIndex: 'domain_account',
      key: 'domain_account',
      width: 120 },
    {
      title: '性别',
      dataIndex: 'gender',
      key: 'gender',
      width: 70 },
    {
      title: '一级部门',
      dataIndex: 'department',
      key: 'department',
      width: 120 },
    {
      title: '二级部门',
      dataIndex: 'sub_department',
      key: 'sub_department',
      width: 120 },
    {
      title: '职务|岗位',
      dataIndex: 'position',
      key: 'position',
      width: 120 },
    {
      title: '职级',
      dataIndex: 'level',
      key: 'level',
      width: 80 },
    {
      title: '联系电话',
      dataIndex: 'phone',
      key: 'phone',
      width: 130 },
    {
      title: '电子邮箱',
      dataIndex: 'email',
      key: 'email',
      width: 180 },
    {
      title: '操作',
      key: 'action',
      width: 120,
      fixed: 'right' as const,
      render: (_: any, record: Employee) => (
        <Space size="small">
          <Tooltip title="查看详情">
            <Button
              type="text"
              size="small"
              icon={<EyeOutlined />}
              onClick={() => onView(record)}
            />
          </Tooltip>
          <Tooltip title="编辑">
            <Button
              type="text"
              size="small"
              icon={<EditOutlined />}
              onClick={() => onEdit(record)}
            />
          </Tooltip>
          <Popconfirm
            title="确认删除"
            description={`确定要删除员工 ${record.name} 吗？`}
            onConfirm={() => handleDelete(record.id)}
            okText="确定"
            cancelText="取消"
          >
            <Tooltip title="删除">
              <Button
                type="text"
                size="small"
                danger
                icon={<DeleteOutlined />}
              />
            </Tooltip>
          </Popconfirm>
        </Space>
      ) },
  ]

  return (
    <Table
      columns={columns}
      dataSource={employees}
      rowKey="id"
      loading={loading}
      pagination={{
        current: page,
        pageSize,
        total,
        showSizeChanger: true,
        showTotal: (t) => `共 ${t} 条`,
        onChange: onPageChange }}
      scroll={{ x: 1400 }}
      size="small"
    />
  )
}
