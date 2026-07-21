'use client'

import { useCallback, useEffect, useState } from 'react'
import {
  App,
  Button,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import {
  LockOutlined,
  PlusOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  UserSwitchOutlined,
} from '@ant-design/icons'
import {
  createUser,
  getUsers,
  resetUserPassword,
  updateUser,
} from '@/actions/users'
import ModulePermissionsDrawer from './ModulePermissionsDrawer'
import type {
  LocalUserCreate,
  UserManagementItem,
  UserManagementUpdate,
} from '@/actions/users'

const { Text } = Typography

const roleOptions = [
  { value: 'user', label: '普通用户' },
  { value: 'admin', label: '管理员' },
]

const statusOptions = [
  { value: 'active', label: '启用' },
  { value: 'disabled', label: '禁用' },
]

export default function UserManagementClient() {
  const { message } = App.useApp()
  const [users, setUsers] = useState<UserManagementItem[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingUser, setEditingUser] = useState<UserManagementItem | null>(null)
  const [saving, setSaving] = useState(false)
  const [passwordUser, setPasswordUser] = useState<UserManagementItem | null>(null)
  const [permissionUser, setPermissionUser] =
    useState<UserManagementItem | null>(null)
  const [keyword, setKeyword] = useState('')
  const [form] = Form.useForm()
  const [passwordForm] = Form.useForm()

  const loadUsers = useCallback(async () => {
    setLoading(true)
    try {
      const result = await getUsers({ keyword: keyword || undefined })
      setUsers(result.items || [])
    } catch (error) {
      console.error(error)
      message.error('加载用户失败')
    } finally {
      setLoading(false)
    }
  }, [keyword, message])

  useEffect(() => {
    const timeoutId = window.setTimeout(() => void loadUsers(), 0)
    return () => window.clearTimeout(timeoutId)
  }, [loadUsers])

  const handleCreate = () => {
    setEditingUser(null)
    form.resetFields()
    form.setFieldsValue({ role: 'user', status: 'active' })
    setModalOpen(true)
  }

  const handleEdit = (record: UserManagementItem) => {
    setEditingUser(record)
    form.setFieldsValue({
      username: record.username,
      name: record.name,
      email: record.email,
      mobile: record.mobile,
      employee_no: record.employee_no,
      department: record.department,
      position: record.position,
      role: record.role,
      status: record.status,
    })
    setModalOpen(true)
  }

  const handleSave = async () => {
    try {
      const values = await form.validateFields()
      setSaving(true)
      if (editingUser) {
        const updateData: UserManagementUpdate = {
          name: values.name,
          email: values.email || null,
          mobile: values.mobile || null,
          employee_no: values.employee_no || null,
          department: values.department || null,
          position: values.position || null,
          role: values.role,
          status: values.status,
        }
        await updateUser(editingUser.id, updateData)
        message.success('用户已更新')
      } else {
        await createUser(values as LocalUserCreate)
        message.success('用户已创建')
      }
      setModalOpen(false)
      loadUsers()
    } catch (error) {
      if (error instanceof Error) message.error(error.message)
    } finally {
      setSaving(false)
    }
  }

  const handleStatus = async (record: UserManagementItem) => {
    const nextStatus = record.status === 'active' ? 'disabled' : 'active'
    try {
      await updateUser(record.id, { status: nextStatus })
      message.success(nextStatus === 'active' ? '用户已启用' : '用户已禁用')
      loadUsers()
    } catch (error) {
      if (error instanceof Error) message.error(error.message)
    }
  }

  const handleResetPassword = async () => {
    if (!passwordUser) return
    try {
      const values = await passwordForm.validateFields()
      await resetUserPassword(passwordUser.id, { password: values.password })
      message.success('密码已重置')
      setPasswordUser(null)
      passwordForm.resetFields()
    } catch (error) {
      if (error instanceof Error) message.error(error.message)
    }
  }

  const columns = [
    {
      title: '用户',
      key: 'user',
      width: 220,
      render: (_: unknown, record: UserManagementItem) => (
        <div>
          <div className="font-medium text-[var(--color-charcoal)]">
            {record.name}
          </div>
          <Text className="text-[12px] text-[var(--color-steel)]">
            {record.username || record.email || record.mobile || '-'}
          </Text>
        </div>
      ),
    },
    {
      title: '角色',
      dataIndex: 'role',
      width: 110,
      render: (role: string) => (
        <Tag color={role === 'admin' ? 'purple' : 'default'}>
          {role === 'admin' ? '管理员' : '普通用户'}
        </Tag>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (status: string) => (
        <Tag color={status === 'active' ? 'success' : 'error'}>
          {status === 'active' ? '启用' : '禁用'}
        </Tag>
      ),
    },
    {
      title: '部门',
      dataIndex: 'department',
      width: 160,
      render: (department: string | null) => department || '-',
    },
    {
      title: '职位',
      dataIndex: 'position',
      width: 160,
      render: (position: string | null) => position || '-',
    },
    {
      title: '来源',
      dataIndex: 'auth_source',
      width: 110,
      render: (source: string) => (
        <Tag>{source === 'feishu' ? '飞书授权' : '本地账号'}</Tag>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 350,
      fixed: 'right' as const,
      render: (_: unknown, record: UserManagementItem) => (
        <Space>
          <Button size="small" onClick={() => handleEdit(record)}>
            编辑
          </Button>
          <Button
            size="small"
            icon={<LockOutlined />}
            onClick={() => setPasswordUser(record)}
          >
            重置密码
          </Button>
          <Button
            size="small"
            icon={<SafetyCertificateOutlined />}
            onClick={() => setPermissionUser(record)}
          >
            模块权限
          </Button>
          <Popconfirm
            title={record.status === 'active' ? '确认禁用该用户？' : '确认启用该用户？'}
            onConfirm={() => handleStatus(record)}
            okText="确定"
            cancelText="取消"
          >
            <Button size="small" danger={record.status === 'active'}>
              {record.status === 'active' ? '禁用' : '启用'}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="m-0 text-[20px] font-semibold text-[var(--color-charcoal)]">
            用户管理
          </h2>
          <Text className="text-[13px] text-[var(--color-steel)]">
            管理开发阶段本地账号，并为飞书 SSO 用户分配平台角色。
          </Text>
        </div>
        <Space>
          <Input.Search
            allowClear
            placeholder="搜索姓名、账号、邮箱"
            onSearch={(value) => setKeyword(value)}
            style={{ width: 260 }}
          />
          <Button icon={<ReloadOutlined />} onClick={loadUsers}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
            新建用户
          </Button>
        </Space>
      </div>

      <Table
        columns={columns}
        dataSource={users}
        rowKey="id"
        loading={loading}
        scroll={{ x: 1050 }}
        pagination={{ pageSize: 10 }}
      />

      <Modal
        title={editingUser ? '编辑用户' : '新建本地用户'}
        open={modalOpen}
        onOk={handleSave}
        onCancel={() => setModalOpen(false)}
        confirmLoading={saving}
        okText="保存"
        cancelText="取消"
        width={640}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item
            name="username"
            label="用户名"
            rules={[{ required: !editingUser, message: '请输入用户名' }]}
          >
            <Input disabled={!!editingUser} placeholder="例如：admin" />
          </Form.Item>
          {!editingUser && (
            <Form.Item
              name="password"
              label="初始密码"
              rules={[{ required: true, min: 6, message: '请输入至少 6 位密码' }]}
            >
              <Input.Password placeholder="至少 6 位" />
            </Form.Item>
          )}
          <Form.Item
            name="name"
            label="姓名"
            rules={[{ required: true, message: '请输入姓名' }]}
          >
            <Input placeholder="用户姓名" />
          </Form.Item>
          <Space size="large" align="start">
            <Form.Item name="role" label="角色" style={{ width: 160 }}>
              <Select options={roleOptions} />
            </Form.Item>
            <Form.Item name="status" label="状态" style={{ width: 160 }}>
              <Select options={statusOptions} />
            </Form.Item>
          </Space>
          <Form.Item name="email" label="邮箱">
            <Input placeholder="name@example.com" />
          </Form.Item>
          <Space size="large" align="start">
            <Form.Item name="mobile" label="手机号" style={{ width: 180 }}>
              <Input />
            </Form.Item>
            <Form.Item name="employee_no" label="工号" style={{ width: 180 }}>
              <Input />
            </Form.Item>
          </Space>
          <Space size="large" align="start">
            <Form.Item name="department" label="部门" style={{ width: 220 }}>
              <Input />
            </Form.Item>
            <Form.Item name="position" label="职位" style={{ width: 220 }}>
              <Input />
            </Form.Item>
          </Space>
        </Form>
      </Modal>

      <Modal
        title={
          <Space>
            <UserSwitchOutlined />
            重置密码
          </Space>
        }
        open={!!passwordUser}
        onOk={handleResetPassword}
        onCancel={() => setPasswordUser(null)}
        okText="保存"
        cancelText="取消"
      >
        <Form form={passwordForm} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item
            name="password"
            label="新密码"
            rules={[{ required: true, min: 6, message: '请输入至少 6 位密码' }]}
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
        </Form>
      </Modal>

      <ModulePermissionsDrawer
        user={permissionUser}
        open={!!permissionUser}
        onClose={() => setPermissionUser(null)}
      />
    </div>
  )
}
