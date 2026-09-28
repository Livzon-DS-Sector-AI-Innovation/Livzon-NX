'use client'

import { useCallback, useEffect, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { App, Button, Dropdown, Form, Input, Modal, Select, Space, Table, Tag, Typography } from 'antd'
import Alert from '@/components/shared/PlatformNotice'
import {
  LockOutlined,
  MoreOutlined,
  PlusOutlined,
  ReloadOutlined,
  TeamOutlined,
  UserSwitchOutlined,
} from '@ant-design/icons'
import {
  createUser,
  getUsers,
  resetUserPassword,
  syncFeishuUsers,
  updateUser,
} from '@/actions/users'
import type {
  LocalUserCreate,
  UserManagementItem,
  UserManagementUpdate,
} from '@/actions/users'

const { Text } = Typography

const roleOptions = [
  { value: 'user', label: '普通用户' },
  { value: 'admin', label: '系统管理员' },
]

const statusOptions = [
  { value: 'active', label: '启用' },
  { value: 'disabled', label: '禁用' },
]

export default function UserManagementClient() {
  const { message, modal } = App.useApp()
  const searchParams = useSearchParams()
  const keyword = searchParams.get('q')?.trim() || ''
  const requestedPage = Number(searchParams.get('page'))
  const page = Number.isSafeInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1
  const requestedSize = Number(searchParams.get('size'))
  const pageSize = [10, 20, 50].includes(requestedSize) ? requestedSize : 10
  const [users, setUsers] = useState<UserManagementItem[]>([])
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingUser, setEditingUser] = useState<UserManagementItem | null>(null)
  const [saving, setSaving] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [passwordUser, setPasswordUser] = useState<UserManagementItem | null>(null)
  const [searchDraft, setSearchDraft] = useState({ keyword, value: keyword })
  const [form] = Form.useForm()
  const [passwordForm] = Form.useForm()

  const searchText = searchDraft.keyword === keyword ? searchDraft.value : keyword

  const updateListUrl = (nextKeyword: string, nextPage: number, nextSize = pageSize) => {
    const params = new URLSearchParams(searchParams.toString())
    params.set('tab', 'users')
    if (nextKeyword) params.set('q', nextKeyword)
    else params.delete('q')
    if (nextPage > 1) params.set('page', String(nextPage))
    else params.delete('page')
    if (nextSize !== 10) params.set('size', String(nextSize))
    else params.delete('size')
    window.history.replaceState(null, '', `/settings?${params.toString()}`)
  }

  const loadUsers = useCallback(async () => {
    setLoading(true)
    setLoadError(false)
    try {
      const result = await getUsers({ keyword: keyword || undefined })
      setUsers(result.items || [])
    } catch (error) {
      console.error(error)
      setLoadError(true)
    } finally {
      setLoading(false)
    }
  }, [keyword])

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

  const handleSyncFeishuUsers = () => {
    modal.confirm({
      title: '同步飞书通讯录用户',
      content:
        '将使用服务端环境变量中的飞书登录与通讯录应用凭证（存在激活的系统配置时优先使用系统配置）读取已授权范围，并更新本地用户、部门和飞书身份信息。现有本地角色与账号状态不会被覆盖。',
      okText: '开始同步',
      cancelText: '取消',
      async onOk() {
        setSyncing(true)
        try {
          const result = await syncFeishuUsers()
          if (result.status === 'warning') message.warning(result.message)
          else message.success(result.message)
          await loadUsers()
        } catch (error) {
          message.error(
            error instanceof Error ? error.message : '飞书用户同步失败'
          )
          throw error
        } finally {
          setSyncing(false)
        }
      },
    })
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
      throw error
    }
  }

  const confirmStatus = (record: UserManagementItem) => {
    const disabling = record.status === 'active'
    modal.confirm({
      title: `确认${disabling ? '禁用' : '启用'}${record.name}？`,
      content: disabling ? '禁用后，该用户将无法继续登录。' : '启用后，该用户可恢复登录。',
      okText: disabling ? '确认禁用' : '确认启用',
      okButtonProps: { danger: disabling },
      cancelText: '取消',
      onOk: () => handleStatus(record),
    })
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
      render: (role: string, record: UserManagementItem) => (
        <Tag color={role === 'admin' ? 'purple' : 'default'}>
          {record.roles?.includes('ordinary_admin') ? '普通管理员' : role === 'admin' ? '系统管理员' : '普通用户'}
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
      width: 150,
      render: (department: string | null) => department || '-',
    },
    {
      title: '职位',
      dataIndex: 'position',
      width: 150,
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
      width: 150,
      fixed: 'right' as const,
      render: (_: unknown, record: UserManagementItem) => (
        <Space size={4}>
          <Button size="small" onClick={() => handleEdit(record)}>
            编辑
          </Button>
          <Dropdown
            trigger={['click']}
            menu={{
              items: [
                { key: 'password', label: '重置密码', icon: <LockOutlined /> },
                {
                  key: 'status',
                  label: record.status === 'active' ? '禁用用户' : '启用用户',
                  danger: record.status === 'active',
                },
              ],
              onClick: ({ key }) => {
                if (key === 'password') setPasswordUser(record)
                if (key === 'status') confirmStatus(record)
              },
            }}
          >
            <Button size="small" icon={<MoreOutlined />} aria-label={`${record.name}的更多操作`}>
              更多
            </Button>
          </Dropdown>
        </Space>
      ),
    },
  ]

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <h3 className="m-0 text-[20px] font-semibold text-[var(--color-charcoal)]">用户列表</h3>
          <Text className="text-[13px] text-[var(--color-steel)]">
            管理开发阶段本地账号，并为飞书 SSO 用户分配平台角色。
          </Text>
        </div>
        <div className="flex w-full flex-wrap items-center gap-2 xl:w-auto">
          <Input.Search
            allowClear
            placeholder="搜索姓名、账号、邮箱"
            value={searchText}
            onChange={(event) => setSearchDraft({ keyword, value: event.target.value })}
            onSearch={(value) => {
              const nextKeyword = value.trim()
              setSearchDraft({ keyword: nextKeyword, value: nextKeyword })
              updateListUrl(nextKeyword, 1)
            }}
            className="w-full sm:w-[260px]"
          />
          <Button icon={<ReloadOutlined />} onClick={loadUsers}>
            刷新
          </Button>
          <Button
            icon={<TeamOutlined />}
            loading={syncing}
            onClick={handleSyncFeishuUsers}
          >
            同步飞书用户
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
            新建用户
          </Button>
        </div>
      </div>

      {loadError && (
        <Alert type="error" showIcon title="用户列表加载失败" description="请重试，当前列表可能不是最新数据。" action={<Button onClick={() => void loadUsers()}>重试</Button>} />
      )}

      <Table
        columns={columns}
        dataSource={users}
        rowKey="id"
        loading={loading}
        scroll={{ x: 990 }}
        locale={{ emptyText: keyword ? '没有符合条件的用户' : '暂无用户' }}
        pagination={{
          current: Math.min(page, Math.max(1, Math.ceil(users.length / pageSize))),
          pageSize,
          pageSizeOptions: ['10', '20', '50'],
          showSizeChanger: true,
          onChange: (nextPage, nextSize) => updateListUrl(keyword, nextPage, nextSize),
        }}
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
          <p className="-mt-3 text-xs text-[var(--color-steel)]">
            普通管理员请在“权限管理 → 用户角色分配”中设置。
          </p>
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
    </div>
  )
}
