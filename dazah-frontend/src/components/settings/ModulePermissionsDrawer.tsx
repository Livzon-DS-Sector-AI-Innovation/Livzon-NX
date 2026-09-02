'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert, App, Button, Checkbox, ConfigProvider, Drawer, Empty, Input, Radio, Segmented,
  Select, Skeleton, Space, Table, Tag, Typography,
} from 'antd'
import { ReloadOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import { getPermissionModuleName } from '@/lib/menu-config'
import { changePageLevels, highRiskPageKeys, PAGE_DATA_SCOPE_VISIBLE, pageGrantChanges } from '@/lib/page-permission-editor'
import { PagePermissionDiff } from '@/components/shared/PagePermissionDiff'
import {
  getPermissionDepartments,
  getUserPagePermissions,
  replaceUserPagePermissions,
} from '@/actions/users'
import type {
  DepartmentResponse,
  EffectivePageGrantOut,
  PageGrantInput,
  PagePermissionDefinitionOut,
  UserManagementItem,
  UserPagePermissionsOut,
} from '@/actions/users'

const { Text, Title } = Typography
type PermissionLevel = 'access' | 'query' | 'operate'
type ScopeType = NonNullable<PageGrantInput['data_scope']>['scope_type']
type EditableGrant = {
  mode: 'inherit' | 'custom'
  permissions: PermissionLevel[]
  sensitiveActions: string[]
  scopeType: ScopeType
  departmentIds: string[]
}

const permissionOptions: Array<{ value: PermissionLevel; label: string; description: string }> = [
  { value: 'access', label: '访问', description: '可以进入并看到这个页面' },
  { value: 'query', label: '查询', description: '可以读取已授权的列表和详情' },
  { value: 'operate', label: '操作', description: '可以新增或修改普通业务数据' },
]
const scopeNames: Record<string, string> = {
  not_applicable: '不适用', department_tree: '本部门及下级',
  departments: '指定部门及下级', all: '全部部门', self: '仅本人',
}
const rolloutNames: Record<string, { label: string; color: string }> = {
  legacy: { label: '旧规则', color: 'default' },
  draft: { label: '配置草稿', color: 'warning' },
  enforced: { label: '已发布', color: 'success' },
}

function normalizePermissions(values: PermissionLevel[]): PermissionLevel[] {
  const selected = new Set(values)
  if (selected.has('operate')) selected.add('query')
  if (selected.has('query')) selected.add('access')
  if (!selected.has('access')) selected.clear()
  else if (!selected.has('query')) selected.delete('operate')
  return permissionOptions.map((option) => option.value).filter((value) => selected.has(value))
}

export function initialPageEditableState(result: UserPagePermissionsOut): Record<string, EditableGrant> {
  const grants = new Map((result.grants || []).map((grant) => [grant.page_key, grant]))
  const custom = new Set(result.custom_page_keys || [])
  return Object.fromEntries((result.definitions || []).map((definition) => {
    const grant = grants.get(definition.page_key)
    return [definition.page_key, {
      mode: custom.has(definition.page_key) ? 'custom' : 'inherit',
      permissions: normalizePermissions((grant?.permissions || []) as PermissionLevel[]),
      sensitiveActions: grant?.sensitive_actions || [],
      scopeType: grant?.data_scope.scope_type || definition.supported_scope_types?.[0] || 'not_applicable',
      departmentIds: grant?.data_scope.department_ids || [],
    }]
  }))
}

export function roleBaselineState(result: UserPagePermissionsOut): Record<string, EditableGrant> {
  return initialPageEditableState({ ...result, grants: result.role_grants || [], custom_page_keys: [] })
}

function sourceLabel(grant?: EffectivePageGrantOut) {
  if (!grant || grant.source === 'none') return <Tag>未授权</Tag>
  if (grant.source === 'super_admin') return <Tag color="gold">系统管理员</Tag>
  if (grant.source === 'user') return <Tag color="blue">用户覆盖</Tag>
  return <span className="flex flex-wrap gap-1">{(grant.source_role_names || []).map((name) => (
    <Tag key={name} color="geekblue">{name}</Tag>
  ))}</span>
}

export default function ModulePermissionsDrawer({ user, open, onClose }: {
  user: UserManagementItem | null
  open: boolean
  onClose: () => void
}) {
  const { message, modal } = App.useApp()
  const loadVersion = useRef(0)
  const savingVersion = useRef<number | null>(null)
  const userId = user?.id
  const [result, setResult] = useState<UserPagePermissionsOut | null>(null)
  const [departments, setDepartments] = useState<DepartmentResponse[]>([])
  const [editable, setEditable] = useState<Record<string, EditableGrant>>({})
  const [moduleCode, setModuleCode] = useState('hr')
  const [filter, setFilter] = useState<'all' | 'authorized' | 'custom'>('all')
  const [reason, setReason] = useState('')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [expandedKeys, setExpandedKeys] = useState<string[]>([])
  const systemAdmin = user?.role === 'admin'

  const load = useCallback(async () => {
    if (!userId) return
    const version = ++loadVersion.current
    setLoading(true)
    setSaving(false)
    savingVersion.current = null
    setResult(null)
    setReason('')
    setErrorMessage('')
    try {
      const [permissions, departmentList] = await Promise.all([
        getUserPagePermissions(userId), PAGE_DATA_SCOPE_VISIBLE ? getPermissionDepartments() : Promise.resolve([]),
      ])
      if (version !== loadVersion.current) return
      if (permissions.user_id !== userId) throw new Error('用户授权返回对象不一致，请重新加载')
      setResult(permissions)
      setDepartments(departmentList)
      setEditable(initialPageEditableState(permissions))
      setExpandedKeys(highRiskPageKeys(permissions.definitions || []))
      if (permissions.definitions?.[0]) setModuleCode(permissions.definitions[0].module_code)
      setReason('')
    } catch (error) {
      if (version !== loadVersion.current) return
      setErrorMessage(error instanceof Error ? error.message : '加载页面权限失败')
    } finally {
      if (version === loadVersion.current) setLoading(false)
    }
  }, [userId])

  useEffect(() => {
    if (!open) return
    const timeoutId = window.setTimeout(() => void load(), 0)
    return () => { window.clearTimeout(timeoutId); loadVersion.current += 1 }
  }, [load, open])

  const grantByPage = useMemo(
    () => new Map((result?.grants || []).map((grant) => [grant.page_key, grant])), [result]
  )
  const modules = useMemo(
    () => Array.from(new Set((result?.definitions || []).map((item) => item.module_code))), [result]
  )
  const definitions = useMemo(() => (result?.definitions || []).filter((item) => {
    if (item.module_code !== moduleCode) return false
    const state = editable[item.page_key]
    if (filter === 'custom') return state?.mode === 'custom'
    if (filter === 'authorized') return Boolean(state?.permissions.length)
    return true
  }), [editable, filter, moduleCode, result])

  const updateGrant = (pageKey: string, patch: Partial<EditableGrant>) => {
    setEditable((current) => ({ ...current, [pageKey]: { ...current[pageKey], ...patch } }))
  }
  const changes = result ? pageGrantChanges(result.definitions || [], initialPageEditableState(result), editable,
    new Map(departments.map((department) => [department.feishu_department_id, department.name]))) : []
  const inCurrentSession = (action: () => void | Promise<void>) => {
    const version = loadVersion.current
    return () => { if (version === loadVersion.current) return action() }
  }
  const confirmDiscard = (action: () => void) => {
    if (!changes.length) return action()
    modal.confirm({ title: '放弃未保存的权限调整？', content: '当前更改尚未保存，继续后将丢失。',
      okText: '放弃更改', cancelText: '继续编辑', onOk: inCurrentSession(action) })
  }
  const setModulePermission = (permission: PermissionLevel | 'none') => {
    setEditable((current) => {
      const next = { ...current }
      for (const definition of result?.definitions || []) {
        if (definition.module_code !== moduleCode) continue
        next[definition.page_key] = {
          ...next[definition.page_key], mode: 'custom',
          permissions: permission === 'none' ? [] : normalizePermissions([permission]),
          sensitiveActions: [],
        }
      }
      return next
    })
  }

  const handleSave = async () => {
    if (systemAdmin || !open || !user || !result || result.user_id !== user.id || loading || saving) return
    const version = loadVersion.current
    if (savingVersion.current === version) return
    if (!reason.trim()) {
      message.warning('请填写本次授权调整原因')
      return
    }
    const grants: PageGrantInput[] = Object.entries(editable).flatMap(([pageKey, state]) =>
      state.mode === 'inherit' ? [] : [{
        page_key: pageKey, mode: 'custom', permissions: state.permissions,
        sensitive_actions: state.sensitiveActions,
        data_scope: {
          scope_type: state.scopeType,
          department_ids: state.scopeType === 'departments' ? state.departmentIds : [],
        },
      }]
    )
    try {
      savingVersion.current = version
      setSaving(true)
      const response = await replaceUserPagePermissions(user.id, {
        expected_grant_version: result.grant_version, grants, reason: reason.trim(),
      })
      if (version !== loadVersion.current) return
      if (!response.ok) throw new Error(response.message)
      const next = response.data
      if (next.user_id !== user.id) throw new Error('用户授权返回对象不一致，请重新加载')
      setResult(next)
      setEditable(initialPageEditableState(next))
      setReason('')
      setErrorMessage('')
      message.success('页面权限已保存')
    } catch (error) {
      if (version !== loadVersion.current) return
      setErrorMessage(`${error instanceof Error ? error.message : '保存页面权限失败'}。本地修改已保留；如版本冲突，请刷新最新授权后重新调整。`)
    } finally {
      if (version === loadVersion.current) {
        savingVersion.current = null
        setSaving(false)
      }
    }
  }

  const previewSave = () => {
    if (!reason.trim()) { message.warning('请填写本次授权调整原因'); return }
    if (!changes.length) { message.info('没有需要保存的权限调整'); return }
    modal.confirm({ title: `确认调整${user?.name || '用户'}的页面权限`, width: 900,
      content: <PagePermissionDiff changes={changes} />, okText: '确认保存', cancelText: '返回修改',
      onOk: inCurrentSession(handleSave) })
  }

  const columns = [
    {
      title: '菜单页面', key: 'page', width: 210,
      render: (_: unknown, definition: PagePermissionDefinitionOut) => <div>
        <Text strong>{definition.page_name}</Text>
        <div className="mt-1">{sourceLabel(grantByPage.get(definition.page_key))}</div>
      </div>,
    },
    {
      title: '权限', key: 'permissions', width: 285,
      render: (_: unknown, definition: PagePermissionDefinitionOut) => {
        const state = editable[definition.page_key]
        return <Checkbox.Group value={state?.permissions || []} disabled={systemAdmin || saving || state?.mode !== 'custom'}
          onChange={(values) => {
            const permissions = changePageLevels(state?.permissions || [], values as PermissionLevel[])
            updateGrant(definition.page_key, { permissions,
              sensitiveActions: permissions.includes('operate') ? state.sensitiveActions : [],
            })
          }}>
          <Space wrap>{permissionOptions.map((option) => <Checkbox key={option.value}
            value={option.value} title={option.description}>{option.label}</Checkbox>)}</Space>
        </Checkbox.Group>
      },
    },
    {
      title: '数据范围', key: 'scope', width: 240,
      render: (_: unknown, definition: PagePermissionDefinitionOut) => {
        const state = editable[definition.page_key]
        const supported = definition.supported_scope_types || []
        return <div className="space-y-2">
          <Select className="w-full" value={state?.scopeType}
            disabled={saving || state?.mode !== 'custom' || supported.length <= 1}
            options={supported.map((value) => ({ value, label: scopeNames[value] || value }))}
            onChange={(value) => updateGrant(definition.page_key, { scopeType: value, departmentIds: [] })} />
          {state?.scopeType === 'departments' && <Select mode="multiple" className="w-full"
            placeholder="选择部门" disabled={saving || state.mode !== 'custom'} value={state.departmentIds}
            options={departments.map((department) => ({
              value: department.feishu_department_id, label: department.name,
            }))}
            onChange={(departmentIds) => updateGrant(definition.page_key, { departmentIds })} />}
        </div>
      },
    },
    {
      title: '授权方式', key: 'mode', width: 190,
      render: (_: unknown, definition: PagePermissionDefinitionOut) => {
        const state = editable[definition.page_key]
        return <Radio.Group optionType="button" buttonStyle="solid" size="small"
          value={state?.mode} options={[
            { label: '角色基线', value: 'inherit' }, { label: '用户覆盖', value: 'custom' },
          ]} onChange={(event) => {
            if (event.target.value === 'inherit' && result) {
              updateGrant(definition.page_key, roleBaselineState(result)[definition.page_key])
            } else updateGrant(definition.page_key, { mode: 'custom' })
          }} />
      },
    },
  ].filter((column) => PAGE_DATA_SCOPE_VISIBLE || column.key !== 'scope')

  return <Drawer title={null} open={open} onClose={() => confirmDiscard(onClose)} size="min(1180px, 100vw)"
    destroyOnHidden footer={<div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <Input disabled={systemAdmin || loading || saving} value={reason} onChange={(event) => setReason(event.target.value)}
        placeholder="填写授权调整原因" maxLength={500} aria-label="授权调整原因" />
      <Space className="shrink-0"><Button onClick={() => confirmDiscard(onClose)}>取消</Button>
        <Button type="primary" loading={saving} onClick={previewSave}
          disabled={systemAdmin || loading || !result || result.user_id !== user?.id}
          icon={<SafetyCertificateOutlined />}>预览并保存授权</Button></Space>
    </div>}>
    <div className="mb-5 border-b border-[var(--color-border)] pb-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div><Title level={3} className="!m-0 !text-[22px]">
          {user?.name || '用户'}的页面权限
        </Title><Text className="mt-1 block text-[13px] text-[var(--color-steel)]">
          权限以单个菜单页面为最小单元；一级模块入口需在“用户角色 → 模块访问”中单独开启。
        </Text></div>
        <Button disabled={saving} icon={<ReloadOutlined />} onClick={() => confirmDiscard(() => void load())} loading={loading}>刷新</Button>
      </div>
      {result && <div className="mt-4 flex flex-wrap items-center gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3">
        <Text type="secondary">授权版本 {result.grant_version}</Text>
        <Text type="secondary">用户覆盖 {result.custom_page_keys?.length || 0} 个页面</Text>
      </div>}
    </div>
    {systemAdmin && <Alert className="mb-4" type="info" showIcon title="系统管理员拥有全部权限，无需逐页配置；页面覆盖不会限制此身份。" />}
    <Alert className="mb-4" type="info" showIcon
      title="角色提供基线，用户覆盖会完整替换单页基线"
      description="选择“用户覆盖”后，权限全部不勾选表示明确拒绝；恢复“角色基线”即可删除覆盖。高风险业务动作在展开行中单独授权。" />
    {errorMessage && <Alert className="mb-4" type="error" showIcon title={errorMessage} />}
    {loading ? <Skeleton active paragraph={{ rows: 10 }} /> : result?.user_id === user?.id && result?.definitions?.length ? <ConfigProvider componentDisabled={systemAdmin || saving}>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <Space wrap><Segmented value={moduleCode} onChange={(value) => setModuleCode(String(value))}
          options={modules.map((code) => ({ value: code, label: <span>{getPermissionModuleName(code)}{' '}
            <Tag color={rolloutNames[result.module_rollouts?.[code] || 'legacy']?.color}>
              {rolloutNames[result.module_rollouts?.[code] || 'legacy']?.label}
            </Tag></span> }))} />
          <Segmented value={filter} onChange={(value) => setFilter(value as typeof filter)} options={[
            { label: '全部页面', value: 'all' }, { label: '只看已授权', value: 'authorized' },
            { label: '只看用户覆盖', value: 'custom' },
          ]} /></Space>
        <Space wrap><Text type="secondary">当前模块内页面批量设置：</Text>
          <Button size="small" onClick={() => setModulePermission('access')}>仅访问</Button>
          <Button size="small" onClick={() => setModulePermission('query')}>只读</Button>
          <Button size="small" onClick={() => setModulePermission('operate')}>可操作</Button>
          <Button size="small" danger onClick={() => setModulePermission('none')}>明确拒绝</Button>
          <Button size="small" onClick={() => {
            const baseline = roleBaselineState(result)
            setEditable((current) => ({ ...current, ...Object.fromEntries((result.definitions || [])
              .filter((definition) => definition.module_code === moduleCode)
              .map((definition) => [definition.page_key, baseline[definition.page_key]])) }))
          }}>恢复角色基线</Button>
        </Space>
      </div>
      <Table rowKey="page_key" columns={columns} dataSource={definitions}
        pagination={{ pageSize: 20, showSizeChanger: true }} size="middle" scroll={{ x: 980 }}
        expandable={{ expandedRowKeys: expandedKeys, onExpandedRowsChange: (keys) => setExpandedKeys(keys.map(String)),
          rowExpandable: (definition) => Boolean(definition.sensitive_actions?.length), expandedRowRender: (definition) => {
          const state = editable[definition.page_key]
          const actions = definition.sensitive_actions || []
          return actions.length ? <div className="px-3 py-2"><Text strong>高风险业务动作</Text>
            <Checkbox.Group className="mt-3 flex flex-wrap gap-3" value={state?.sensitiveActions || []}
              disabled={systemAdmin || saving || state?.mode !== 'custom'} onChange={(values) => updateGrant(definition.page_key, {
                sensitiveActions: values as string[],
                permissions: values.length ? normalizePermissions([...(state?.permissions || []), 'operate']) : state?.permissions || [],
              })}>{actions.map((action) => <Checkbox key={action.key} value={action.key}
                title={action.description}>{action.name}</Checkbox>)}</Checkbox.Group>
          </div> : <Text type="secondary">此页面没有独立高风险动作。</Text>
        } }} />
    </ConfigProvider> : <Empty description="未加载到有效菜单页面" />}
  </Drawer>
}
