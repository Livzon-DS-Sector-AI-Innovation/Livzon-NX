'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Alert, App, Button, Checkbox, Drawer, Empty, Input, Skeleton, Space, Table, Tag, Typography } from 'antd'
import { ReloadOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import { getUserModulePermissions, replaceUserModulePermissions } from '@/actions/users'
import type {
  ModulePermissionDefinitionOut,
  ModulePermissionGrantInput,
  ModulePermissionKey,
  UserModulePermissionsOut,
} from '@/actions/users'

const { Text, Title } = Typography

export interface ModuleAccessUser {
  id: string
  name: string
  isSystemAdmin: boolean
}

function selectedModuleCodes(result: UserModulePermissionsOut): string[] {
  return (result.grants || [])
    .filter((grant) => (grant.permissions || []).includes('module.view'))
    .map((grant) => grant.module_code)
    .sort()
}

function sameSelection(left: string[], right: string[]) {
  return [...left].sort().join('\0') === [...right].sort().join('\0')
}

export default function UserModuleAccessDrawer({
  user,
  open,
  onClose,
}: {
  user: ModuleAccessUser | null
  open: boolean
  onClose: () => void
}) {
  const { message, modal } = App.useApp()
  const sessionVersion = useRef(0)
  const userId = user?.id
  const [result, setResult] = useState<UserModulePermissionsOut | null>(null)
  const [selectedCodes, setSelectedCodes] = useState<string[]>([])
  const [reason, setReason] = useState('')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')

  const load = useCallback(async () => {
    if (!userId) return
    const version = ++sessionVersion.current
    setLoading(true)
    setSaving(false)
    setResult(null)
    setReason('')
    setErrorMessage('')
    try {
      const next = await getUserModulePermissions(userId)
      if (version !== sessionVersion.current) return
      if (next.user_id !== userId) throw new Error('用户授权返回对象不一致，请重新加载')
      setResult(next)
      setSelectedCodes(selectedModuleCodes(next))
    } catch (error) {
      if (version !== sessionVersion.current) return
      setErrorMessage(error instanceof Error ? error.message : '加载模块访问权限失败')
    } finally {
      if (version === sessionVersion.current) setLoading(false)
    }
  }, [userId])

  useEffect(() => {
    if (!open) return
    const timeoutId = window.setTimeout(() => void load(), 0)
    return () => {
      window.clearTimeout(timeoutId)
      sessionVersion.current += 1
    }
  }, [load, open])

  const originalCodes = useMemo(() => result ? selectedModuleCodes(result) : [], [result])
  const changed = !sameSelection(originalCodes, selectedCodes)
  const selected = useMemo(() => new Set(selectedCodes), [selectedCodes])

  const setModuleAccess = (moduleCode: string, allowed: boolean) => {
    setSelectedCodes((current) => {
      const next = new Set(current)
      if (allowed) next.add(moduleCode)
      else next.delete(moduleCode)
      return [...next].sort()
    })
  }

  const close = () => {
    if (!changed) return onClose()
    const version = sessionVersion.current
    modal.confirm({
      title: '放弃未保存的模块访问调整？',
      content: '关闭后，本次模块访问开关变更将丢失。',
      okText: '放弃更改',
      cancelText: '继续编辑',
      onOk: () => {
        if (version === sessionVersion.current) onClose()
      },
    })
  }

  const save = async () => {
    if (!user || !result || !open || saving || loading || user.isSystemAdmin) return
    if (!reason.trim()) {
      message.warning('请填写本次模块访问调整原因')
      return
    }
    const version = sessionVersion.current
    const grantByModule = new Map((result.grants || []).map((grant) => [grant.module_code, grant]))
    const grants: ModulePermissionGrantInput[] = selectedCodes.map((moduleCode) => {
      const current = grantByModule.get(moduleCode)
      const permissions = new Set<ModulePermissionKey>(current?.permissions || [])
      permissions.add('module.view')
      return {
        module_code: moduleCode,
        permissions: [...permissions].sort(),
        data_scope: current?.data_scope || {},
      }
    })
    try {
      setSaving(true)
      const next = await replaceUserModulePermissions(user.id, {
        expected_grant_version: result.grant_version,
        grants,
        reason: reason.trim(),
      })
      if (version !== sessionVersion.current) return
      if (next.user_id !== user.id) throw new Error('用户授权返回对象不一致，请重新加载')
      setResult(next)
      setSelectedCodes(selectedModuleCodes(next))
      setReason('')
      setErrorMessage('')
      message.success('模块访问权限已保存')
    } catch (error) {
      if (version !== sessionVersion.current) return
      setErrorMessage(`${error instanceof Error ? error.message : '保存模块访问权限失败'}。本地修改已保留，请核对后重试。`)
    } finally {
      if (version === sessionVersion.current) setSaving(false)
    }
  }

  const previewSave = () => {
    if (!changed) {
      message.info('没有需要保存的模块访问调整')
      return
    }
    if (!reason.trim()) {
      message.warning('请填写本次模块访问调整原因')
      return
    }
    const added = selectedCodes.filter((code) => !originalCodes.includes(code)).length
    const removed = originalCodes.filter((code) => !selected.has(code)).length
    const version = sessionVersion.current
    modal.confirm({
      title: `确认调整${user?.name || '用户'}的模块访问权限`,
      content: `将新增 ${added} 个模块访问入口，移除 ${removed} 个模块访问入口。移除后用户将无法进入对应模块。`,
      okText: '确认保存',
      cancelText: '返回修改',
      onOk: () => {
        if (version === sessionVersion.current) return save()
      },
    })
  }

  const columns = [
    {
      title: '模块',
      key: 'module',
      render: (_: unknown, module: ModulePermissionDefinitionOut) => (
        <div>
          <Text strong>{module.module_name}</Text>
          <div className="mt-1 text-[12px] text-[var(--color-steel)]">{module.description}</div>
        </div>
      ),
    },
    {
      title: '访问状态',
      key: 'access',
      width: 150,
      render: (_: unknown, module: ModulePermissionDefinitionOut) => (
        <Checkbox
          checked={selected.has(module.module_code)}
          disabled={user?.isSystemAdmin || saving}
          onChange={(event) => setModuleAccess(module.module_code, event.target.checked)}
        >
          {selected.has(module.module_code) ? '允许访问' : '禁止访问'}
        </Checkbox>
      ),
    },
  ]

  return (
    <Drawer
      title={null}
      open={open}
      onClose={close}
      size="min(820px, 100vw)"
      destroyOnHidden
      footer={(
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <Input
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="填写模块访问调整原因"
            maxLength={500}
            disabled={user?.isSystemAdmin || loading || saving}
          />
          <Space className="shrink-0">
            <Button onClick={close}>取消</Button>
            <Button
              type="primary"
              icon={<SafetyCertificateOutlined />}
              loading={saving}
              disabled={user?.isSystemAdmin || loading || !result}
              onClick={previewSave}
            >
              预览并保存
            </Button>
          </Space>
        </div>
      )}
    >
      <div className="mb-5 border-b border-[var(--color-border)] pb-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <Title level={3} className="!m-0 !text-[22px]">
              {user?.name || '用户'}的模块访问权限
            </Title>
            <Text className="mt-1 block text-[13px] text-[var(--color-steel)]">
              控制用户能否进入一级业务模块；模块内页面和操作权限仍由已分配角色决定。
            </Text>
          </div>
          <Button icon={<ReloadOutlined />} loading={loading} disabled={saving} onClick={() => void load()}>
            刷新
          </Button>
        </div>
        {result && (
          <div className="mt-4 flex flex-wrap items-center gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3">
            <Text type="secondary">授权版本 {result.grant_version}</Text>
            <Tag color="blue">已允许 {selectedCodes.length} 个模块</Tag>
          </div>
        )}
      </div>

      {user?.isSystemAdmin && (
        <Alert
          className="mb-4"
          type="info"
          showIcon
          title="系统管理员默认拥有全部模块访问权限，不能在此限制。"
        />
      )}
      {result?.livzon_sync_status === 'failed' && (
        <Alert
          className="mb-4"
          type="warning"
          showIcon
          title="模块访问已保存，但 Livzon 范围同步失败"
          description={result.livzon_last_error || '请检查能力注册状态后重试。'}
        />
      )}
      {errorMessage && (
        <Alert
          className="mb-4"
          type="error"
          showIcon
          title={errorMessage}
          action={<Button size="small" onClick={() => void load()}>重试</Button>}
        />
      )}

      {loading && !result ? (
        <Skeleton active paragraph={{ rows: 8 }} />
      ) : result?.available_modules?.length ? (
        <>
          <div className="mb-3 flex flex-wrap justify-end gap-2">
            <Button
              size="small"
              disabled={user?.isSystemAdmin || saving}
              onClick={() => setSelectedCodes((result.available_modules || []).map((module) => module.module_code).sort())}
            >
              全部允许
            </Button>
            <Button
              size="small"
              danger
              disabled={user?.isSystemAdmin || saving}
              onClick={() => setSelectedCodes([])}
            >
              全部关闭
            </Button>
          </div>
          <Table
            rowKey="module_code"
            columns={columns}
            dataSource={result.available_modules}
            pagination={false}
            size="middle"
            scroll={{ x: 620 }}
          />
        </>
      ) : (
        !loading && <Empty description="未加载到可配置模块" />
      )}
    </Drawer>
  )
}
