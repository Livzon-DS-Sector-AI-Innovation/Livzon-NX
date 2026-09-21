'use client'

import { useCallback, useDeferredValue, useEffect, useMemo, useRef, useState } from 'react'
import {
  Alert, App, Button, Checkbox, ConfigProvider, Drawer, Empty, Input, Radio, Segmented,
  Select, Skeleton, Space, Table, Tag, Typography,
} from 'antd'
import { ReloadOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { getPermissionModuleName } from '@/lib/menu-config'
import {
  highRiskPageKeys, PAGE_DATA_SCOPE_VISIBLE, pageGrantChanges, pagePermissionTier,
  pageGrantChangeKind, pagePermissionTierLabel, pagePermissionTierOptions, permissionsForTier,
  pageScopeIssue, pageScopeSummary, type PageGrantChangeKind, type PagePermissionTier,
} from '@/lib/page-permission-editor'
import { PagePermissionDiff } from '@/components/shared/PagePermissionDiff'
import { PagePermissionHistoryDrawer } from '@/components/shared/PagePermissionHistoryDrawer'
import { SensitiveActionExpiryEditor, sensitiveActionExpiryFromDays } from '@/components/shared/SensitiveActionExpiryEditor'
import {
  getPermissionDepartments,
  getUserPagePermissions,
  replaceUserPagePermissions,
} from '@/actions/users'
import type {
  DepartmentResponse,
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
  sensitiveActionsExpiresAt: string | null
}

const scopeNames: Record<string, string> = {
  not_applicable: '待接入数据范围', department_tree: '本部门及下级',
  departments: '指定部门及下级', all: '本页面全部数据', self: '仅本人',
  production_fermentation: '发酵数据', production_extraction: '提炼数据',
}
const integrationNames: Record<string, { label: string; color: string }> = {
  incomplete: { label: '接入有缺口', color: 'error' },
  passed: { label: '自动检查通过', color: 'success' },
}

function normalizePermissions(values: PermissionLevel[]): PermissionLevel[] {
  const selected = new Set(values)
  if (selected.has('operate')) selected.add('query')
  if (selected.has('query')) selected.add('access')
  if (!selected.has('access')) selected.clear()
  else if (!selected.has('query')) selected.delete('operate')
  return (['access', 'query', 'operate'] as PermissionLevel[]).filter((value) => selected.has(value))
}

export function initialPageEditableState(result: UserPagePermissionsOut): Record<string, EditableGrant> {
  const grants = new Map((result.grants || []).map((grant) => [grant.page_key, grant]))
  const customGrants = new Map((result.custom_grants || []).map((grant) => [grant.page_key, grant]))
  const custom = new Set(result.custom_page_keys || [])
  return Object.fromEntries((result.definitions || []).map((definition) => {
    const grant = custom.has(definition.page_key)
      ? customGrants.get(definition.page_key) || grants.get(definition.page_key)
      : grants.get(definition.page_key)
    return [definition.page_key, {
      mode: custom.has(definition.page_key) ? 'custom' : 'inherit',
      permissions: normalizePermissions((grant?.permissions || []) as PermissionLevel[]),
      sensitiveActions: grant?.sensitive_actions || [],
      scopeType: grant?.data_scope.scope_type || definition.supported_scope_types?.[0] || 'all',
      departmentIds: grant?.data_scope.department_ids || [],
      sensitiveActionsExpiresAt: Object.values(grant?.sensitive_action_expirations || {})
        .find((value) => value != null) || null,
    }]
  }))
}

export function roleBaselineState(result: UserPagePermissionsOut): Record<string, EditableGrant> {
  return initialPageEditableState({ ...result, grants: result.role_grants || [], custom_page_keys: [] })
}

const overrideComparisons: Record<PageGrantChangeKind, { label: string; color: string }> = {
  grant: { label: '覆盖新增', color: 'green' }, expand: { label: '覆盖扩大', color: 'gold' },
  restrict: { label: '覆盖收紧', color: 'orange' }, revoke: { label: '明确拒绝', color: 'red' },
  mixed: { label: '组合差异', color: 'blue' }, source: { label: '结果与基线相同', color: 'default' },
}

export default function ModulePermissionsDrawer({ user, open, onClose }: {
  user: UserManagementItem | null
  open: boolean
  onClose: () => void
}) {
  const { message, modal } = App.useApp()
  const loadVersion = useRef(0)
  const savingVersion = useRef<number | null>(null)
  const pendingIdempotencyKey = useRef<string | null>(null)
  const userId = user?.id
  const [result, setResult] = useState<UserPagePermissionsOut | null>(null)
  const [departments, setDepartments] = useState<DepartmentResponse[]>([])
  const [editable, setEditable] = useState<Record<string, EditableGrant>>({})
  const [moduleCode, setModuleCode] = useState('hr')
  const [filter, setFilter] = useState<'all' | 'authorized' | 'custom' | 'different' | 'sensitive' | 'changed'>('all')
  const [search, setSearch] = useState('')
  const deferredSearch = useDeferredValue(search)
  const [reason, setReason] = useState('')
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [expandedKeys, setExpandedKeys] = useState<string[]>([])
  const [historyOpen, setHistoryOpen] = useState(false)
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
        getUserPagePermissions(userId), getPermissionDepartments(),
      ])
      if (version !== loadVersion.current) return
      if (permissions.user_id !== userId) throw new Error('用户授权返回对象不一致，请重新加载')
      setResult(permissions)
      setDepartments(departmentList)
      setEditable(initialPageEditableState(permissions))
      setExpandedKeys(highRiskPageKeys(permissions.definitions || []))
      setFilter('all')
      setSearch('')
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

  const roleBaseline = useMemo(() => result ? roleBaselineState(result) : {}, [result])
  const roleGrantByPage = useMemo(
    () => new Map((result?.role_grants || []).map((grant) => [grant.page_key, grant])), [result]
  )
  const modules = useMemo(
    () => Array.from(new Set((result?.definitions || []).map((item) => item.module_code))), [result]
  )
  const initialEditable = useMemo(() => result ? initialPageEditableState(result) : {}, [result])
  const changes = useMemo(() => result ? pageGrantChanges(result.definitions || [], initialEditable, editable,
    new Map(departments.map((department) => [department.feishu_department_id, department.name]))) : [],
  [departments, editable, initialEditable, result])
  const changedPageKeys = useMemo(() => new Set(changes.map((change) => change.pageKey)), [changes])
  const activeDepartmentIds = useMemo(() => new Set(
    departments.map((department) => department.feishu_department_id)), [departments])
  const scopeIssues = useMemo(() => (result?.definitions || []).flatMap((definition) => {
    const state = editable[definition.page_key]
    if (state?.mode !== 'custom') return []
    const issue = pageScopeIssue(state.scopeType, state.departmentIds,
      definition.supported_scope_types || [], activeDepartmentIds)
    return issue ? [`${definition.page_name}：${issue}`] : []
  }), [activeDepartmentIds, editable, result])
  const riskIssues = useMemo(() => (result?.definitions || []).flatMap((definition) => {
    const state = editable[definition.page_key]
    if (state?.mode !== 'custom' || !state.sensitiveActions.length) return []
    if (!state.sensitiveActionsExpiresAt) return [`${definition.page_name}：请设置高风险权限到期时间`]
    if (dayjs(state.sensitiveActionsExpiresAt).isBefore(dayjs())) return [`${definition.page_name}：高风险权限到期时间必须晚于当前时间`]
    return []
  }), [editable, result])
  const definitions = useMemo(() => (result?.definitions || []).filter((item) => {
    if (item.module_code !== moduleCode) return false
    if (deferredSearch.trim() && !`${item.page_name} ${item.page_key}`.toLowerCase().includes(deferredSearch.trim().toLowerCase())) return false
    const state = editable[item.page_key]
    if (filter === 'custom') return state?.mode === 'custom'
    if (filter === 'different') return state?.mode === 'custom' &&
      pageGrantChangeKind(roleBaseline[item.page_key], state) !== 'source'
    if (filter === 'sensitive') return Boolean(item.sensitive_actions?.length)
    if (filter === 'authorized') return Boolean(state?.permissions.length)
    if (filter === 'changed') return changedPageKeys.has(item.page_key)
    return true
  }), [changedPageKeys, deferredSearch, editable, filter, moduleCode, result, roleBaseline])

  const updateGrant = (pageKey: string, patch: Partial<EditableGrant>) => {
    setEditable((current) => ({ ...current, [pageKey]: { ...current[pageKey], ...patch } }))
  }
  const inCurrentSession = (action: () => void | Promise<void>) => {
    const version = loadVersion.current
    return () => { if (version === loadVersion.current) return action() }
  }
  const confirmDiscard = (action: () => void) => {
    if (!changes.length) return action()
    modal.confirm({ title: '放弃未保存的权限调整？', content: '当前更改尚未保存，继续后将丢失。',
      okText: '放弃更改', cancelText: '继续编辑', onOk: inCurrentSession(action) })
  }
  const setVisiblePermission = (permission: PagePermissionTier) => {
    const targetKeys = definitions.map((definition) => definition.page_key)
    if (!targetKeys.length) { message.info('当前筛选没有可调整的页面'); return }
    modal.confirm({
      title: `批量设为“${pagePermissionTierOptions.find((option) => option.value === permission)?.label}”？`,
      content: `将调整当前筛选结果中的 ${targetKeys.length} 个页面；筛选外页面保持不变。`,
      okText: `调整 ${targetKeys.length} 个页面`, cancelText: '取消',
      onOk: inCurrentSession(() => {
        setEditable((current) => {
          const next = { ...current }
          for (const pageKey of targetKeys) {
            const previous = next[pageKey]
            const permissions = permissionsForTier(permission)
            next[pageKey] = {
              ...previous, mode: 'custom', permissions,
              sensitiveActions: permissions.includes('operate') ? previous.sensitiveActions : [],
            }
          }
          return next
        })
        message.info(`已调整 ${targetKeys.length} 个页面，保存后生效`)
      }),
    })
  }
  const restoreVisibleBaseline = () => {
    const targetKeys = definitions.map((definition) => definition.page_key)
    if (!targetKeys.length || !result) { message.info('当前筛选没有可恢复的页面'); return }
    modal.confirm({
      title: '恢复当前筛选页面的角色基线？',
      content: `将删除 ${targetKeys.length} 个页面的用户覆盖，恢复为角色提供的权限；筛选外页面保持不变。`,
      okText: `恢复 ${targetKeys.length} 个页面`, cancelText: '取消',
      onOk: inCurrentSession(() => {
        const baseline = roleBaselineState(result)
        setEditable((current) => ({ ...current,
          ...Object.fromEntries(targetKeys.map((pageKey) => [pageKey, baseline[pageKey]])) }))
        message.info(`已恢复 ${targetKeys.length} 个页面的角色基线，保存后生效`)
      }),
    })
  }

  const updateVisibleSensitiveActions = (mode: 'renew' | 'revoke') => {
    const targetKeys = definitions.map((item) => item.page_key).filter((pageKey) =>
      editable[pageKey]?.mode === 'custom' && editable[pageKey]?.sensitiveActions.length)
    if (!targetKeys.length) { message.info('当前筛选没有用户覆盖的高风险动作'); return }
    const verb = mode === 'renew' ? '续期 30 天' : '撤销'
    modal.confirm({
      title: `批量${verb}高风险权限？`,
      content: `将处理当前筛选结果中的 ${targetKeys.length} 个页面。`,
      okText: `确认${verb}`, cancelText: '取消',
      onOk: inCurrentSession(() => {
        setEditable((current) => ({
          ...current,
          ...Object.fromEntries(targetKeys.map((pageKey) => [pageKey, {
            ...current[pageKey],
            sensitiveActions: mode === 'revoke' ? [] : current[pageKey].sensitiveActions,
            sensitiveActionsExpiresAt: mode === 'revoke' ? null : sensitiveActionExpiryFromDays(30),
          }])),
        }))
        message.info(`已${verb} ${targetKeys.length} 个页面的高风险权限，保存后生效`)
      }),
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
        sensitive_actions_expires_at: state.sensitiveActionsExpiresAt,
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
        idempotency_key: pendingIdempotencyKey.current ?? crypto.randomUUID(),
      })
      if (version !== loadVersion.current) return
      if (!response.ok) throw new Error(response.message)
      const next = response.data
      if (next.user_id !== user.id) throw new Error('用户授权返回对象不一致，请重新加载')
      setResult(next)
      setEditable(initialPageEditableState(next))
      setReason('')
      pendingIdempotencyKey.current = null
      setErrorMessage('')
      message.success('页面权限已保存并生效')
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
    if (scopeIssues.length) { message.error(scopeIssues[0]); return }
    if (riskIssues.length) { message.error(riskIssues[0]); return }
    pendingIdempotencyKey.current = crypto.randomUUID()
    modal.confirm({ title: `确认调整${user?.name || '用户'}的页面权限`, width: 900,
      content: <PagePermissionDiff changes={changes}
        impactNote="这些调整只影响当前用户；角色基线和其他用户不会改变。用户覆盖会完整替换对应页面的角色基线。" />,
      okText: '确认保存', cancelText: '返回修改',
      onOk: inCurrentSession(handleSave),
      onCancel: () => { pendingIdempotencyKey.current = null } })
  }

  const columns = [
    {
      title: '菜单页面', key: 'page', width: 210,
      render: (_: unknown, definition: PagePermissionDefinitionOut) => <div>
        <Space size={4} wrap><Text strong>{definition.page_name}</Text>
          {changedPageKeys.has(definition.page_key) && <Tag color="orange">未保存</Tag>}</Space>
        <Text type="secondary" className="mt-1 block text-xs">{definition.page_key}</Text>
      </div>,
    },
    {
      title: '授权来源与角色对照', key: 'source', width: 250,
      render: (_: unknown, definition: PagePermissionDefinitionOut) => {
        const state = editable[definition.page_key]
        const baseline = roleBaseline[definition.page_key]
        const roleGrant = roleGrantByPage.get(definition.page_key)
        const roleNames = roleGrant?.source_role_names || []
        const roleSources = roleGrant?.role_sources || []
        if (state?.mode !== 'custom') return <div>
          <Tag color="geekblue">继承角色基线</Tag>
          <Text type="secondary" className="mt-1 block text-xs">
            {roleNames.length ? `${roleNames.join('、')} · ${pagePermissionTierLabel(baseline?.permissions || [])}` : '当前角色未提供页面权限'}
          </Text>
          {roleSources.length > 1 && <div className="mt-1 space-y-0.5">
            {roleSources.map((source) => <Text key={source.role_id} type="secondary" className="block text-xs">
              {source.role_name}：{pagePermissionTierLabel(source.permissions || [])}，{pageScopeSummary(
                source.data_scope.scope_type, source.data_scope.department_ids || [],
                new Map(departments.map((department) => [department.feishu_department_id, department.name])), definition.page_key)}
            </Text>)}
          </div>}
        </div>
        const comparison = overrideComparisons[pageGrantChangeKind(baseline, state)]
        return <div><Space size={4} wrap><Tag color="blue">用户覆盖</Tag>
          <Tag color={comparison.color}>{comparison.label}</Tag></Space>
          <Text type="secondary" className="mt-1 block text-xs">
            角色基线：{pagePermissionTierLabel(baseline?.permissions || [])}{roleNames.length ? `（${roleNames.join('、')}）` : ''}
          </Text>
          <Text type="secondary" className="mt-1 block text-xs">
            用户覆盖完整替换该页角色基线
          </Text>
        </div>
      },
    },
    {
      title: '权限档位', key: 'permissions', width: 330,
      render: (_: unknown, definition: PagePermissionDefinitionOut) => {
        const state = editable[definition.page_key]
        return <Radio.Group size="small" optionType="button" buttonStyle="solid"
          value={pagePermissionTier(state?.permissions || [])}
          disabled={systemAdmin || saving || state?.mode !== 'custom'}
          options={pagePermissionTierOptions.map(({ value, label, description }) => ({ value, label, title: description }))}
          onChange={(event) => {
            const permissions = permissionsForTier(event.target.value as PagePermissionTier)
            updateGrant(definition.page_key, { permissions,
              sensitiveActions: permissions.includes('operate') ? state.sensitiveActions : [],
            })
          }} />
      },
    },
    {
      title: '最终状态', key: 'effective', width: 150,
      render: (_: unknown, definition: PagePermissionDefinitionOut) => {
        if (!systemAdmin && !(user?.module_codes || []).includes(definition.module_code)) {
          return <Tag color="warning">模块入口未开通</Tag>
        }
        const permissions = editable[definition.page_key]?.permissions || []
        return <Tag color={permissions.length ? 'success' : 'default'}>{pagePermissionTierLabel(permissions)}</Tag>
      },
    },
    {
      title: '数据范围', key: 'scope', width: 240,
      render: (_: unknown, definition: PagePermissionDefinitionOut) => {
        const state = editable[definition.page_key]
        const supported = definition.supported_scope_types || []
        if (!PAGE_DATA_SCOPE_VISIBLE) return <Tag>{pageScopeSummary(
          state?.scopeType || 'all', state?.departmentIds || [],
          new Map(departments.map((department) => [department.feishu_department_id, department.name])), definition.page_key,
        )}</Tag>
        return <div className="space-y-2">
          <Select className="w-full" value={state?.scopeType}
            disabled={saving || state?.mode !== 'custom' || supported.length <= 1}
            options={supported.map((value) => ({ value, label: value === 'all' && definition.page_key === 'production:overview' ? '全部生产数据' : scopeNames[value] || value }))}
            onChange={(value) => updateGrant(definition.page_key, { scopeType: value, departmentIds: [] })} />
          {state?.scopeType === 'departments' && <Select mode="multiple" className="w-full"
            placeholder="选择部门" disabled={saving || state.mode !== 'custom'} value={state.departmentIds}
            options={departments.map((department) => ({
              value: department.feishu_department_id, label: department.name,
            }))} status={pageScopeIssue(state.scopeType, state.departmentIds,
              supported, activeDepartmentIds) ? 'error' : undefined}
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
  ]

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
        <Space><Button disabled={saving || !result} onClick={() => setHistoryOpen(true)}>授权历史</Button>
          <Button disabled={saving} icon={<ReloadOutlined />} onClick={() => confirmDiscard(() => void load())} loading={loading}>刷新</Button></Space>
      </div>
      {result && <div className="mt-4 flex flex-wrap items-center gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3">
        <Text type="secondary">授权版本 {result.grant_version}</Text>
        <Text type="secondary">用户覆盖 {result.custom_page_keys?.length || 0} 个页面</Text>
        <Text type={changes.length ? 'warning' : 'secondary'}>未保存调整 {changes.length} 个页面</Text>
      </div>}
    </div>
    {systemAdmin && <Alert className="mb-4" type="info" showIcon title="系统管理员拥有全部权限，无需逐页配置；页面覆盖不会限制此身份。" />}
    <Alert className="mb-4" type="info" showIcon
      title="角色提供基线，用户覆盖会完整替换单页基线"
      description="保存后权限立即生效，无需经过权限接入检查。选择“用户覆盖”后，权限全部不勾选表示明确拒绝；恢复“角色基线”即可删除覆盖。高风险操作是“普通操作”之上的附加授权：勾选时自动启用普通操作，取消普通操作时一并撤销。" />
    {errorMessage && <Alert className="mb-4" type="error" showIcon title={errorMessage} />}
    {!!scopeIssues.length && <Alert className="mb-4" type="warning" showIcon
      title="存在无法保存的数据范围" description={scopeIssues.slice(0, 3).join('；')} />}
    {!!riskIssues.length && <Alert className="mb-4" type="warning" showIcon
      title="高风险权限需要有效期限" description={riskIssues.slice(0, 3).join('；')} />}
    {loading ? <Skeleton active paragraph={{ rows: 10 }} /> : result?.user_id === user?.id && result?.definitions?.length ? <ConfigProvider componentDisabled={systemAdmin || saving}>
      {!(systemAdmin || (user?.module_codes || []).includes(moduleCode)) && <Alert className="mb-4" type="warning" showIcon
        title="当前用户尚未开通此模块入口"
        description="页面权限可以先配置，但用户需要同时获得模块访问权限后才能进入这些页面。" />}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <Space wrap><Segmented value={moduleCode} onChange={(value) => setModuleCode(String(value))}
          options={modules.map((code) => ({ value: code, label: <span>{getPermissionModuleName(code)}{' '}
            <Tag color={integrationNames[result.module_checks?.[code] || 'incomplete']?.color}>
              {integrationNames[result.module_checks?.[code] || 'incomplete']?.label}
            </Tag></span> }))} />
          <Segmented value={filter} onChange={(value) => setFilter(value as typeof filter)} options={[
            { label: '全部页面', value: 'all' }, { label: '只看已授权', value: 'authorized' },
            { label: '只看用户覆盖', value: 'custom' }, { label: '只看覆盖差异', value: 'different' },
            { label: '只看含高风险操作', value: 'sensitive' },
            { label: `只看未保存 (${changes.length})`, value: 'changed' },
          ]} /></Space>
        <Input.Search allowClear className="max-w-64" placeholder="搜索页面名称或权限键" value={search}
          aria-label="搜索用户页面权限" onChange={(event) => setSearch(event.target.value)} />
        <Space wrap><Text type="secondary">批量调整当前筛选 {definitions.length} 个页面：</Text>
          <Button size="small" onClick={() => setVisiblePermission('access')}>仅入口</Button>
          <Button size="small" onClick={() => setVisiblePermission('query')}>可查看</Button>
          <Button size="small" onClick={() => setVisiblePermission('operate')}>普通操作</Button>
          <Button size="small" danger onClick={() => setVisiblePermission('none')}>无权限</Button>
          <Button size="small" onClick={restoreVisibleBaseline}>恢复角色基线</Button>
          <Button size="small" onClick={() => updateVisibleSensitiveActions('renew')}>高风险续期 30 天</Button>
          <Button size="small" danger onClick={() => updateVisibleSensitiveActions('revoke')}>撤销高风险权限</Button>
        </Space>
      </div>
      <Table rowKey="page_key" columns={columns} dataSource={definitions}
        pagination={{ pageSize: 20, showSizeChanger: true, pageSizeOptions: [10, 20, 50, 100],
          showTotal: (count) => `当前筛选 ${count} 个页面`, hideOnSinglePage: definitions.length <= 20 }}
        size="middle" scroll={{ x: 1240, y: 520 }}
        locale={{ emptyText: search.trim() ? '当前筛选没有匹配页面' : '当前模块暂无可配置页面' }}
        expandable={{ expandedRowKeys: expandedKeys, onExpandedRowsChange: (keys) => setExpandedKeys(keys.map(String)),
          rowExpandable: (definition) => Boolean(definition.sensitive_actions?.length), expandedRowRender: (definition) => {
          const state = editable[definition.page_key]
          const actions = definition.sensitive_actions || []
          return actions.length ? <div className="px-3 py-2"><Space wrap size={6}>
            <Text strong>附加高风险操作</Text><Tag color="orange">依赖普通操作</Tag>
          </Space>
            <Text type="secondary" className="mt-1 block text-xs">勾选后自动启用普通操作；取消普通操作会同时撤销这些权限。</Text>
            <Checkbox.Group className="mt-3 flex flex-wrap gap-3" value={state?.sensitiveActions || []}
              disabled={systemAdmin || saving || state?.mode !== 'custom'} onChange={(values) => updateGrant(definition.page_key, {
                sensitiveActions: values as string[],
                sensitiveActionsExpiresAt: values.length ? state?.sensitiveActionsExpiresAt || null : null,
                permissions: values.length ? normalizePermissions([...(state?.permissions || []), 'operate']) : state?.permissions || [],
              })}>{actions.map((action) => <Checkbox key={action.key} value={action.key}
                title={action.description}>{action.name}</Checkbox>)}</Checkbox.Group>
            {!!state?.sensitiveActions.length && <SensitiveActionExpiryEditor
              disabled={systemAdmin || saving || state.mode !== 'custom'}
              value={state.sensitiveActionsExpiresAt}
              onChange={(value) => updateGrant(definition.page_key, { sensitiveActionsExpiresAt: value })}
              onRevoke={() => updateGrant(definition.page_key, {
                sensitiveActions: [], sensitiveActionsExpiresAt: null,
              })} />}
          </div> : <Text type="secondary">此页面没有独立高风险动作。</Text>
        } }} />
    </ConfigProvider> : <Empty description="未加载到有效菜单页面" />}
    {user && result && <PagePermissionHistoryDrawer targetType="user" targetId={user.id}
      targetName={user.name} grantVersion={result.grant_version} open={historyOpen}
      onClose={() => setHistoryOpen(false)} onRolledBack={load} />}
  </Drawer>
}
