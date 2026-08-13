'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Checkbox,
  Drawer,
  Empty,
  Input,
  Skeleton,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import {
  CheckCircleOutlined,
  ReloadOutlined,
  SafetyCertificateOutlined,
  SyncOutlined,
  WarningOutlined,
} from '@ant-design/icons'
import {
  getUserModulePermissions,
  replaceUserModulePermissions,
  syncUserLivzonAccessScope,
} from '@/actions/users'
import type {
  ModulePermissionDefinitionOut,
  ModulePermissionGrantOut,
  ModulePermissionKey,
  UserManagementItem,
  UserModulePermissionsOut,
} from '@/actions/users'

const { Text, Title } = Typography

export const permissionOptions: Array<{
  value: ModulePermissionKey
  label: string
  description: string
}> = [
  {
    value: 'module.view',
    label: '查看模块',
    description: '进入模块并查看数据范围内的信息',
  },
  {
    value: 'module.agent.read',
    label: 'Livzon 查询',
    description: '允许助手调用模块只读能力',
  },
  {
    value: 'module.agent.execute',
    label: 'Livzon 执行',
    description: '允许确认后调用受控写能力',
  },
  {
    value: 'module.agent.automate',
    label: '自动化',
    description: '允许把模块能力加入定时任务或流程',
  },
]

const defaultModulePermissions = permissionOptions.map((option) => option.value)

type EditableModuleGrant = {
  permissions: ModulePermissionKey[]
  dataScopeText: string
}

function syncStatusTag(status?: string | null) {
  if (status === 'synced') {
    return (
      <Tag icon={<CheckCircleOutlined />} color="success">
        已同步
      </Tag>
    )
  }
  if (status === 'failed') {
    return (
      <Tag icon={<WarningOutlined />} color="error">
        同步失败
      </Tag>
    )
  }
  return <Tag color="warning">尚未同步</Tag>
}

export function initialEditableState(
  result: UserModulePermissionsOut
): Record<string, EditableModuleGrant> {
  const grants = new Map(
    (result.grants || []).map((grant) => [grant.module_code, grant])
  )
  return Object.fromEntries(
    (result.available_modules || []).map((module) => {
      const grant = grants.get(module.module_code)
      return [
        module.module_code,
        {
          permissions: grant
            ? permissionOptions
                .map((option) => option.value)
                .filter((permission) =>
                  (grant.permissions || []).includes(permission)
                )
            : [...defaultModulePermissions],
          dataScopeText: JSON.stringify(grant?.data_scope || {}, null, 2),
        },
      ]
    })
  )
}

export default function ModulePermissionsDrawer({
  user,
  open,
  onClose,
}: {
  user: UserManagementItem | null
  open: boolean
  onClose: () => void
}) {
  const { message } = App.useApp()
  const [result, setResult] = useState<UserModulePermissionsOut | null>(null)
  const [editable, setEditable] = useState<
    Record<string, EditableModuleGrant>
  >({})
  const [reason, setReason] = useState('')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [syncing, setSyncing] = useState(false)

  const load = useCallback(async () => {
    if (!user) return
    setLoading(true)
    try {
      const next = await getUserModulePermissions(user.id)
      setResult(next)
      setEditable(initialEditableState(next))
      setReason('')
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载模块权限失败')
    } finally {
      setLoading(false)
    }
  }, [message, user])

  useEffect(() => {
    if (!open) return
    const timeoutId = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timeoutId)
  }, [load, open])

  const grantByModule = useMemo(
    () =>
      new Map(
        (result?.grants || []).map((grant) => [grant.module_code, grant])
      ),
    [result]
  )

  const updatePermissions = (
    moduleCode: string,
    values: ModulePermissionKey[]
  ) => {
    const normalized = values.length
      ? Array.from(new Set<ModulePermissionKey>(['module.view', ...values]))
      : []
    setEditable((current) => ({
      ...current,
      [moduleCode]: {
        permissions: normalized,
        dataScopeText: current[moduleCode]?.dataScopeText || '{}',
      },
    }))
  }

  const handleSave = async () => {
    if (!user || !result) return
    if (!reason.trim()) {
      message.warning('请填写本次授权调整原因')
      return
    }
    try {
      const grants = (result.available_modules || []).flatMap((module) => {
        const item = editable[module.module_code]
        if (!item?.permissions.length) return []
        const parsed = JSON.parse(item.dataScopeText || '{}') as unknown
        if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
          throw new Error(`${module.module_name}的数据范围必须是 JSON 对象`)
        }
        return [
          {
            module_code: module.module_code,
            permissions: item.permissions,
            data_scope: parsed as Record<string, unknown>,
          },
        ]
      })
      setSaving(true)
      const next = await replaceUserModulePermissions(user.id, {
        expected_grant_version: result.grant_version,
        grants,
        reason: reason.trim(),
      })
      setResult(next)
      setEditable(initialEditableState(next))
      setReason('')
      if (next.livzon_sync_status === 'synced') {
        message.success('模块授权已保存，Livzon 范围已同步')
      } else {
        message.warning('模块授权已保存，Livzon 范围同步仍需重试')
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存模块权限失败')
    } finally {
      setSaving(false)
    }
  }

  const handleSync = async () => {
    if (!user) return
    setSyncing(true)
    try {
      await syncUserLivzonAccessScope(user.id)
      message.success('Livzon 范围已重新同步')
      await load()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '同步 Livzon 范围失败')
    } finally {
      setSyncing(false)
    }
  }

  const columns = [
    {
      title: '模块',
      key: 'module',
      width: 180,
      render: (_: unknown, module: ModulePermissionDefinitionOut) => (
        <div>
          <Text strong>{module.module_name}</Text>
          <div className="mt-1 text-[12px] text-[var(--color-steel)]">
            {module.module_code}
          </div>
        </div>
      ),
    },
    {
      title: '权限项',
      key: 'permissions',
      render: (_: unknown, module: ModulePermissionDefinitionOut) => (
        <Checkbox.Group
          value={editable[module.module_code]?.permissions || []}
          onChange={(values) =>
            updatePermissions(
              module.module_code,
              values as ModulePermissionKey[]
            )
          }
          className="grid grid-cols-1 gap-x-4 gap-y-2 xl:grid-cols-2"
        >
          {permissionOptions.map((option) => (
            <Checkbox key={option.value} value={option.value}>
              <span title={option.description}>{option.label}</span>
            </Checkbox>
          ))}
        </Checkbox.Group>
      ),
    },
  ]

  return (
    <Drawer
      title={null}
      open={open}
      onClose={onClose}
      size="min(920px, 100vw)"
      destroyOnHidden
      footer={
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <Input
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="填写授权调整原因"
            maxLength={500}
            aria-label="授权调整原因"
          />
          <Space className="shrink-0">
            <Button onClick={onClose}>取消</Button>
            <Button
              type="primary"
              loading={saving}
              onClick={handleSave}
              icon={<SafetyCertificateOutlined />}
            >
              保存授权
            </Button>
          </Space>
        </div>
      }
    >
      <div className="mb-5 border-b border-[var(--color-border)] pb-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <Title level={3} className="!m-0 !text-[22px]">
              {user?.name || '用户'}的模块权限
            </Title>
            <Text className="mt-1 block text-[13px] text-[var(--color-steel)]">
              未配置的模块默认开启全部可配置权限，保存后同步到 Livzon 范围。
            </Text>
          </div>
          <Space wrap>
            <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>
              刷新
            </Button>
            <Button
              icon={<SyncOutlined spin={syncing} />}
              onClick={handleSync}
              disabled={!result}
            >
              重新同步
            </Button>
          </Space>
        </div>
        {result && (
          <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3">
            <span>
              <Text type="secondary">授权版本 </Text>
              <Text strong>{result.grant_version}</Text>
            </span>
            <span>
              <Text type="secondary">Livzon 来源版本 </Text>
              <Text strong>{result.livzon_source_grant_version ?? '-'}</Text>
            </span>
            <span>
              <Text type="secondary">同步状态 </Text>
              {syncStatusTag(result.livzon_sync_status)}
            </span>
          </div>
        )}
      </div>

      {result?.livzon_sync_status === 'failed' && (
        <Alert
          className="mb-4"
          type="warning"
          showIcon
          message="授权已保存，但 Livzon 范围同步失败"
          description={
            result.livzon_last_error || '请检查能力注册状态后重新同步。'
          }
        />
      )}

      {loading && !result ? (
        <Skeleton active paragraph={{ rows: 8 }} />
      ) : result?.available_modules?.length ? (
        <Table
          rowKey="module_code"
          columns={columns}
          dataSource={result.available_modules}
          pagination={false}
          size="middle"
          scroll={{ x: 760 }}
          expandable={{
            expandedRowRender: (module) => {
              const grant = grantByModule.get(module.module_code) as
                | ModulePermissionGrantOut
                | undefined
              return (
                <div className="grid gap-4 px-2 py-2 lg:grid-cols-[1fr_280px]">
                  <div>
                    <Text type="secondary">{module.description}</Text>
                    {grant && (
                      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-[var(--color-steel)]">
                        <span>授权人：{grant.granted_by}</span>
                        <span>
                          更新时间：{new Date(grant.updated_at).toLocaleString()}
                        </span>
                        <span>生效版本：{grant.grant_version}</span>
                      </div>
                    )}
                  </div>
                  <div>
                    <Text className="mb-1 block text-[12px] font-medium">
                      数据范围 JSON
                    </Text>
                    <Input.TextArea
                      value={editable[module.module_code]?.dataScopeText || '{}'}
                      onChange={(event) =>
                        setEditable((current) => ({
                          ...current,
                          [module.module_code]: {
                            permissions:
                              current[module.module_code]?.permissions || [],
                            dataScopeText: event.target.value,
                          },
                        }))
                      }
                      autoSize={{ minRows: 3, maxRows: 8 }}
                      spellCheck={false}
                      aria-label={`${module.module_name}数据范围 JSON`}
                    />
                  </div>
                </div>
              )
            },
          }}
        />
      ) : (
        <Empty description="未加载到可授权模块" />
      )}
    </Drawer>
  )
}
