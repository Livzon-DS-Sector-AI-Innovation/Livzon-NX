'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { App, Button, Dropdown, Form, Input, Modal, Select, Space, Table, Tag, Typography } from 'antd'
import Alert from '@/components/shared/PlatformNotice'
import { roleTagColor } from '@/lib/role-tag'
import { positiveListNumber } from '@/lib/list-url-state'
import { useListUrlState } from '@/lib/useListUrlState'
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

const roleFilterOptions = [
  { value: 'admin', label: '管理员' },
  { value: 'user', label: '普通用户' },
]

const statusOptions = [
  { value: 'active', label: '启用' },
  { value: 'disabled', label: '禁用' },
]

interface UserFormValues {
  username?: string
  password?: string
  name: string
  email?: string | null
  mobile?: string | null
  employee_no?: string | null
  department?: string | null
  position?: string | null
  role?: 'admin' | 'user'
  status: 'active' | 'disabled'
}

export default function UserManagementClient() {
  const { message, modal } = App.useApp()
  const { page, params, setListQuery } = useListUrlState(10)
  const keyword = params.get('q')?.trim() || ''
  const roleParam = params.get('role')
  const roleFilter = roleParam === 'admin' || roleParam === 'user' ? roleParam : undefined
  const statusParam = params.get('status')
  const statusFilter = statusParam === 'active' || statusParam === 'disabled' ? statusParam : undefined
  // Keep old `size` links working while new links use the project-wide `page_size`.
  const legacySize = positiveListNumber(params.get('size'), 0, 200)
  const pageSize = positiveListNumber(params.get('page_size'), legacySize || 10, 200)

  const [users, setUsers] = useState<UserManagementItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingUser, setEditingUser] = useState<UserManagementItem | null>(null)
  const [saving, setSaving] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [passwordUser, setPasswordUser] = useState<UserManagementItem | null>(null)
  const [searchDraft, setSearchDraft] = useState({ keyword, value: keyword })
  const [form] = Form.useForm<UserFormValues>()
  const [passwordForm] = Form.useForm()
  const requestSequence = useRef(0)

  const searchText = searchDraft.keyword === keyword ? searchDraft.value : keyword

  const loadUsers = useCallback(async () => {
    const sequence = ++requestSequence.current
    setLoading(true)
    setLoadError(false)
    try {
      const result = await getUsers({
        keyword: keyword || undefined,
        role: roleFilter,
        status: statusFilter,
        offset: (page - 1) * pageSize,
        limit: pageSize,
      })
      if (sequence !== requestSequence.current) return
      setUsers(result.items || [])
      setTotal(result.total || 0)
    } catch (error) {
      if (sequence !== requestSequence.current) return
      console.error(error)
      setLoadError(true)
    } finally {
      if (sequence === requestSequence.current) setLoading(false)
    }
  }, [keyword, page, pageSize, roleFilter, statusFilter])

  useEffect(() => {
    const timeoutId = window.setTimeout(() => void loadUsers(), 0)
    return () => window.clearTimeout(timeoutId)
  }, [loadUsers])

  useEffect(() => {
    if (loading || total <= 0) return
    const lastPage = Math.max(1, Math.ceil(total / pageSize))
    if (page > lastPage) setListQuery({ page: lastPage })
  }, [loading, page, pageSize, setListQuery, total])

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
    form.resetFields()
    form.setFieldsValue({
      username: record.username ?? undefined,
      name: record.name,
      email: record.email,
      mobile: record.mobile,
      employee_no: record.employee_no,
      department: record.department,
      position: record.position,
      status: record.status,
    })
    setModalOpen(true)
  }

  const saveUser = async (values: UserFormValues) => {
    setSaving(true)
    try {
      if (editingUser) {
        const updateData: UserManagementUpdate = {
          name: values.name,
          email: values.email || null,
          mobile: values.mobile || null,
          employee_no: values.employee_no || null,
          department: values.department || null,
          position: values.position || null,
          status: values.status,
        }
        await updateUser(editingUser.id, updateData)
        message.success('用户已更新')
      } else {
        const username = values.username?.trim()
        if (!username || !values.password) throw new Error('请填写用户名和初始密码')
        const createData: LocalUserCreate = {
          username,
          password: values.password,
          name: values.name,
          email: values.email || null,
          mobile: values.mobile || null,
          employee_no: values.employee_no || null,
          department: values.department || null,
          position: values.position || null,
          role: values.role ?? 'user',
          status: values.status,
        }
        await createUser(createData)
        message.success('用户已创建')
      }
      setModalOpen(false)
      await loadUsers()
    } catch (error) {
      if (error instanceof Error) message.error(error.message)
    } finally {
      setSaving(false)
    }
  }

  const handleSave = async () => {
    let values: UserFormValues
    try {
      values = await form.validateFields()
    } catch {
      return
    }
    if (!editingUser && values.role === 'admin') {
      modal.confirm({
        title: '确认创建系统管理员？',
        content: '该账号将立即拥有全部平台权限，包括用户、权限、审计和 LLM 配置管理。',
        okText: '创建系统管理员',
        cancelText: '取消',
        okButtonProps: { danger: true },
        onOk: () => saveUser(values),
      })
      return
    }
    await saveUser(values)
  }

  const handleStatus = async (record: UserManagementItem) => {
    const nextStatus = record.status === 'active' ? 'disabled' : 'active'
    try {
      await updateUser(record.id, { status: nextStatus })
      message.success(nextStatus === 'active' ? '用户已启用' : '用户已禁用')
      await loadUsers()
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
      render: (role: string, record: UserManagementItem) => {
        const code = record.roles?.includes('super_admin') ? 'super_admin'
          : record.roles?.includes('ordinary_admin') ? 'ordinary_admin'
          : role === 'admin' ? 'super_admin' : 'user'
        return <Tag color={roleTagColor(code)}>
          {code === 'super_admin' ? '系统管理员' : code === 'ordinary_admin' ? '普通管理员' : '普通用户'}
        </Tag>
      },
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
          <p className="m-0 mt-1 text-xs text-[var(--color-steel)]">
            角色调整请在“权限管理 → 用户角色”中完成，变更需填写原因。
          </p>
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
              setListQuery({ q: nextKeyword || null }, true)
            }}
            className="w-full sm:w-[260px]"
          />
          <Select
            allowClear
            aria-label="角色筛选"
            placeholder="全部角色"
            value={roleFilter}
            options={roleFilterOptions}
            style={{ width: 130 }}
            onChange={(value) => setListQuery({ role: value ?? null }, true)}
          />
          <Select
            allowClear
            aria-label="状态筛选"
            placeholder="全部状态"
            value={statusFilter}
            options={statusOptions}
            style={{ width: 120 }}
            onChange={(value) => setListQuery({ status: value ?? null }, true)}
          />
          <Button icon={<ReloadOutlined />} onClick={() => void loadUsers()}>
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
        locale={{ emptyText: keyword || roleFilter || statusFilter ? '没有符合条件的用户' : '暂无用户' }}
        pagination={{
          current: page,
          pageSize,
          total,
          pageSizeOptions: ['10', '20', '50'],
          showSizeChanger: true,
          showTotal: (value) => `共 ${value} 个账号`,
          onChange: (nextPage, nextSize) => {
            setListQuery(
              nextSize === pageSize
                ? { page: nextPage }
                : { page_size: nextSize, size: null },
              nextSize !== pageSize,
            )
          },
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
          {!editingUser && (
            <Form.Item
              name="role"
              label="初始角色"
              extra="系统管理员拥有全部平台权限；创建后也可在权限管理中调整。"
            >
              <Select options={roleOptions} />
            </Form.Item>
          )}
          <Form.Item name="status" label="状态" style={{ width: 160 }}>
            <Select options={statusOptions} />
          </Form.Item>
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
