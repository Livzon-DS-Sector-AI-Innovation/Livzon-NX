"use client"

import { useDeferredValue, useEffect, useMemo, useRef, useState } from "react"
import { Alert, App, Button, Checkbox, ConfigProvider, Drawer, Input, Radio, Segmented, Select, Space, Table, Tag, Typography } from "antd"
import dayjs from "dayjs"
import {
  getRolePagePermissions,
  previewRolePagePermissions,
  replaceRolePagePermissions,
  type RolePagePermissionsOut,
} from "@/actions/admin"
import type { RoleItem } from "@/lib/api/client/admin"
import type { DepartmentItem } from "@/lib/api/server/admin"
import { getPermissionModuleName } from "@/lib/menu-config"
import {
  PAGE_DATA_SCOPE_VISIBLE, pageGrantChanges, pagePermissionTier, pagePermissionTierLabel,
  pagePermissionTierOptions, pageScopeIssue, pageScopeSummary, permissionsForTier, type PagePermissionTier,
} from "@/lib/page-permission-editor"
import type { ColumnsType } from "antd/es/table"
import { buildPermissionTree, filterAuthorizedTree, type PermissionTreeNode } from "./rolePagePermissionTree"
import { PagePermissionDiff } from "@/components/shared/PagePermissionDiff"
import { PagePermissionHistoryDrawer } from "@/components/shared/PagePermissionHistoryDrawer"
import { SensitiveActionExpiryEditor, sensitiveActionExpiryFromDays } from "@/components/shared/SensitiveActionExpiryEditor"

type Level = "access" | "query" | "operate"
type Grant = {
  permissions: Level[]
  sensitiveActions: string[]
  scopeType: "not_applicable" | "department_tree" | "departments" | "all" | "self" | "production_fermentation" | "production_extraction"
  departmentIds: string[]
  sensitiveActionsExpiresAt: string | null
}
const order: Level[] = ["access", "query", "operate"]
const scopeNames: Record<string, string> = {
  not_applicable: "待接入数据范围", department_tree: "本部门及下级",
  departments: "指定部门及下级", all: "本页面全部数据", self: "仅本人",
  production_fermentation: "发酵数据", production_extraction: "提炼数据",
}

function normalize(values: Level[]): Level[] {
  const selected = new Set(values)
  if (selected.has("operate")) selected.add("query")
  if (selected.has("query")) selected.add("access")
  if (!selected.has("access")) selected.clear()
  else if (!selected.has("query")) selected.delete("operate")
  return order.filter((value) => selected.has(value))
}

function editableState(result: RolePagePermissionsOut): Record<string, Grant> {
  const existing = new Map((result.grants || []).map((grant) => [grant.page_key, grant]))
  return Object.fromEntries((result.definitions || []).map((definition) => {
    const grant = existing.get(definition.page_key)
    return [definition.page_key, {
      permissions: normalize((grant?.permissions || []) as Level[]),
      sensitiveActions: grant?.sensitive_actions || [],
      scopeType: grant?.data_scope.scope_type || definition.supported_scope_types?.[0] || "all",
      departmentIds: grant?.data_scope.department_ids || [],
      sensitiveActionsExpiresAt: Object.values(grant?.sensitive_action_expirations || {})
        .find((value) => value != null) || null,
    }]
  }))
}

export function RolePagePermissionsDrawer({ role, departments, open, onClose }: {
  role: RoleItem | null
  departments: DepartmentItem[]
  open: boolean
  onClose: () => void
}) {
  const { message, modal } = App.useApp()
  const loadVersion = useRef(0)
  const savingVersion = useRef<number | null>(null)
  const pendingIdempotencyKey = useRef<string | null>(null)
  const roleId = role?.id
  const [result, setResult] = useState<RolePagePermissionsOut | null>(null)
  const [editable, setEditable] = useState<Record<string, Grant>>({})
  const [moduleCode, setModuleCode] = useState("hr")
  const [reason, setReason] = useState("")
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [previewing, setPreviewing] = useState(false)
  const [errorMessage, setErrorMessage] = useState("")
  const [refreshVersion, setRefreshVersion] = useState(0)
  const [authorizedOnly, setAuthorizedOnly] = useState(false)
  const [sensitiveOnly, setSensitiveOnly] = useState(false)
  const [search, setSearch] = useState("")
  const deferredSearch = useDeferredValue(search)
  const [expandedKeys, setExpandedKeys] = useState<string[]>([])
  const [historyOpen, setHistoryOpen] = useState(false)

  useEffect(() => {
    const version = ++loadVersion.current
    if (!open || !roleId) return
    queueMicrotask(() => {
      if (version !== loadVersion.current) return
      setLoading(true)
      setSaving(false)
      setPreviewing(false)
      savingVersion.current = null
      setResult(null)
      setReason("")
      setErrorMessage("")
      void getRolePagePermissions(roleId).then((next) => {
        if (version !== loadVersion.current) return
        if (next.role_id !== roleId) throw new Error("角色授权返回对象不一致，请重新加载")
        setResult(next)
        setEditable(editableState(next))
        setExpandedKeys([])
        setAuthorizedOnly(false)
        setSensitiveOnly(false)
        setSearch("")
        if (next.definitions?.[0]) setModuleCode(next.definitions[0].module_code)
        setReason("")
        setErrorMessage("")
      }).catch((error) => { if (version === loadVersion.current) setErrorMessage(error instanceof Error ? error.message : "加载角色页面权限失败") })
        .finally(() => { if (version === loadVersion.current) setLoading(false) })
    })
    return () => { loadVersion.current += 1 }
  }, [open, roleId, refreshVersion])

  const modules = useMemo(() => Array.from(new Set(
    (result?.definitions || []).map((definition) => definition.module_code),
  )), [result])
  const moduleDefinitions = useMemo(() => (result?.definitions || []).filter(
    (definition) => result?.role_id === roleId && definition.module_code === moduleCode,
  ), [result, roleId, moduleCode])
  const visibleDefinitions = useMemo(() => moduleDefinitions.filter((definition) => {
    if (authorizedOnly && !editable[definition.page_key]?.permissions.length) return false
    if (sensitiveOnly && !definition.sensitive_actions?.length) return false
    return !deferredSearch.trim() || `${definition.page_name} ${definition.page_key}`.toLowerCase().includes(deferredSearch.trim().toLowerCase())
  }), [authorizedOnly, deferredSearch, editable, moduleDefinitions, sensitiveOnly])
  const tree = useMemo(() => buildPermissionTree(visibleDefinitions), [visibleDefinitions])
  const definitions = authorizedOnly ? filterAuthorizedTree(tree, editable) : tree
  const allGroupKeys = (nodes: PermissionTreeNode[]): string[] => nodes.flatMap((node) =>
    node.children?.length ? [node.page_key, ...allGroupKeys(node.children)] : [])
  const update = (pageKey: string, patch: Partial<Grant>) => setEditable((current) => ({
    ...current, [pageKey]: { ...current[pageKey], ...patch },
  }))
  const changes = result ? pageGrantChanges(result.definitions || [], editableState(result), editable,
    new Map(departments.map((department) => [department.feishu_department_id, department.name]))) : []
  const changedPageKeys = new Set(changes.map((change) => change.pageKey))
  const activeDepartmentIds = new Set(departments.map((department) => department.feishu_department_id))
  const scopeIssues = (result?.definitions || []).flatMap((definition) => {
    const grant = editable[definition.page_key]
    if (!grant?.permissions.length && !grant?.sensitiveActions.length) return []
    const issue = pageScopeIssue(grant.scopeType, grant.departmentIds,
      definition.supported_scope_types || [], activeDepartmentIds)
    return issue ? [`${definition.page_name}：${issue}`] : []
  })
  const riskIssues = (result?.definitions || []).flatMap((definition) => {
    const grant = editable[definition.page_key]
    if (!grant?.sensitiveActions.length) return []
    if (!grant.sensitiveActionsExpiresAt) return [`${definition.page_name}：请设置高风险权限到期时间`]
    if (dayjs(grant.sensitiveActionsExpiresAt).isBefore(dayjs())) return [`${definition.page_name}：高风险权限到期时间必须晚于当前时间`]
    return []
  })
  const inCurrentSession = (action: () => void | Promise<void>) => {
    const version = loadVersion.current
    return () => { if (version === loadVersion.current) return action() }
  }
  const close = () => {
    if (!changes.length) return onClose()
    modal.confirm({ title: "放弃未保存的角色授权？", content: "当前更改尚未保存，继续后将丢失。",
      okText: "放弃更改", cancelText: "继续编辑", onOk: inCurrentSession(onClose) })
  }
  const roleGrants = () => Object.entries(editable).flatMap(([pageKey, grant]) =>
    grant.permissions.length || grant.sensitiveActions.length ? [{
      page_key: pageKey,
      mode: "custom" as const,
      permissions: grant.permissions,
      sensitive_actions: grant.sensitiveActions,
      sensitive_actions_expires_at: grant.sensitiveActionsExpiresAt,
      data_scope: {
        scope_type: grant.scopeType,
        department_ids: grant.scopeType === "departments" ? grant.departmentIds : [],
      },
    }] : [],
  )

  const save = async () => {
    if (!open || !role || !result || result.role_id !== role.id || loading || saving) return
    const version = loadVersion.current
    if (savingVersion.current === version) return
    if (!reason.trim()) {
      message.warning("请填写本次角色授权调整原因")
      return
    }
    savingVersion.current = version
    setSaving(true)
    try {
      const response = await replaceRolePagePermissions(role.id, {
        expected_grant_version: result.grant_version,
        grants: roleGrants(),
        reason: reason.trim(),
        idempotency_key: pendingIdempotencyKey.current ?? crypto.randomUUID(),
      })
      if (version !== loadVersion.current) return
      if (!response.ok) throw new Error(response.message)
      const next = response.data
      if (next.role_id !== role.id) throw new Error("角色授权返回对象不一致，请重新加载")
      setResult(next)
      setEditable(editableState(next))
      setReason("")
      pendingIdempotencyKey.current = null
      setErrorMessage("")
      message.success("角色页面权限已保存")
    } catch (error) {
      if (version !== loadVersion.current) return
      setErrorMessage(`${error instanceof Error ? error.message : "保存角色页面权限失败"}。本地修改已保留；如版本冲突，请刷新最新授权后重新调整。`)
    } finally {
      if (version === loadVersion.current) {
        savingVersion.current = null
        setSaving(false)
      }
    }
  }

  const previewSave = async () => {
    if (previewing) return
    if (!reason.trim()) { message.warning("请填写本次角色授权调整原因"); return }
    if (!changes.length) { message.info("没有需要保存的权限调整"); return }
    if (scopeIssues.length) { message.error(scopeIssues[0]); return }
    if (riskIssues.length) { message.error(riskIssues[0]); return }
    if (!role || !result) return
    const version = loadVersion.current
    const idempotencyKey = crypto.randomUUID()
    pendingIdempotencyKey.current = idempotencyKey
    setPreviewing(true)
    try {
      const impact = await previewRolePagePermissions(role.id, {
        expected_grant_version: result.grant_version,
        grants: roleGrants(),
        reason: reason.trim(),
        idempotency_key: idempotencyKey,
      })
      if (version !== loadVersion.current) return
      modal.confirm({ title: `确认调整${role.name}的页面权限`, width: 960,
        content: <PagePermissionDiff changes={changes} impactNote={<div className="space-y-1">
          <div>角色成员 {impact.member_count} 人，实际权限会变化 {impact.affected_user_count} 人：</div>
          <div>权限扩大 {impact.expanded_user_count} 人；权限收紧 {impact.restricted_user_count} 人；混合变化 {impact.mixed_user_count} 人。</div>
          <div>其中 {impact.users_with_overrides} 人在本次变化涉及的页面设置了用户覆盖，最终结果已按覆盖优先计算。</div>
          {!!impact.affected_user_samples?.length && <div>影响样例：{impact.affected_user_samples.map((item) => item.user_name).join("、")}</div>}
        </div>} />, okText: "确认保存", cancelText: "返回修改",
        onOk: inCurrentSession(save), onCancel: () => { pendingIdempotencyKey.current = null } })
    } catch (error) {
      if (version === loadVersion.current) setErrorMessage(error instanceof Error ? error.message : "角色授权影响预演失败")
    } finally {
      if (version === loadVersion.current) setPreviewing(false)
    }
  }

  const setVisiblePermission = (tier: PagePermissionTier) => {
    const targetKeys = visibleDefinitions.map((definition) => definition.page_key)
    if (!targetKeys.length) { message.info("当前筛选没有可调整的页面"); return }
    modal.confirm({
      title: `批量设为“${pagePermissionTierOptions.find((option) => option.value === tier)?.label}”？`,
      content: `将调整当前筛选结果中的 ${targetKeys.length} 个页面；筛选外页面保持不变。`,
      okText: `调整 ${targetKeys.length} 个页面`, cancelText: "取消",
      onOk: inCurrentSession(() => {
        setEditable((current) => ({
          ...current,
          ...Object.fromEntries(targetKeys.map((pageKey) => {
            const previous = current[pageKey]
            const permissions = permissionsForTier(tier)
            return [pageKey, { ...previous, permissions,
              sensitiveActions: permissions.includes("operate") ? previous.sensitiveActions : [] }]
          })),
        }))
        message.info(`已调整 ${targetKeys.length} 个页面，保存后生效`)
      }),
    })
  }

  const updateVisibleSensitiveActions = (mode: "renew" | "revoke") => {
    const targetKeys = visibleDefinitions.map((item) => item.page_key)
      .filter((pageKey) => editable[pageKey]?.sensitiveActions.length)
    if (!targetKeys.length) { message.info("当前筛选没有已授权的高风险动作"); return }
    const verb = mode === "renew" ? "续期 30 天" : "撤销"
    modal.confirm({
      title: `批量${verb}高风险权限？`,
      content: `将处理当前筛选结果中的 ${targetKeys.length} 个页面。`,
      okText: `确认${verb}`, cancelText: "取消",
      onOk: inCurrentSession(() => {
        setEditable((current) => ({
          ...current,
          ...Object.fromEntries(targetKeys.map((pageKey) => [pageKey, {
            ...current[pageKey],
            sensitiveActions: mode === "revoke" ? [] : current[pageKey].sensitiveActions,
            sensitiveActionsExpiresAt: mode === "revoke" ? null : sensitiveActionExpiryFromDays(30),
          }])),
        }))
        message.info(`已${verb} ${targetKeys.length} 个页面的高风险权限，保存后生效`)
      }),
    })
  }

  return <Drawer title={`${role?.name || "角色"} · 页面权限基线`} open={open} onClose={close}
    extra={<Button onClick={() => setHistoryOpen(true)} disabled={!result}>授权历史</Button>}
    loading={loading} size="min(1080px, 100vw)" footer={<div className="flex gap-3">
      <Input disabled={loading || saving || previewing} value={reason} onChange={(event) => setReason(event.target.value)}
        placeholder="填写角色授权调整原因" maxLength={500} />
      <Button type="primary" loading={saving || previewing} onClick={() => void previewSave()}
        disabled={loading || !result || result.role_id !== role?.id}>预览并保存基线</Button>
    </div>}>
    <Typography.Paragraph type="secondary">
      这里只配置可访问模块内的菜单页面和基础权限档位，不会开启一级模块入口；高风险操作是“普通操作”之上的附加授权，勾选时会自动启用普通操作，取消普通操作时会一并撤销。用户有精确覆盖时，以用户覆盖为准。
    </Typography.Paragraph>
    {errorMessage && <Alert className="mb-4" type="error" showIcon title={errorMessage}
      action={<Button size="small" onClick={() => modal.confirm({ title: "重新加载最新角色授权？",
        content: "刷新会放弃未保存的本地调整，请先核对需要保留的更改。", okText: "重新加载", cancelText: "继续编辑",
        onOk: inCurrentSession(() => { setLoading(true); setRefreshVersion((version) => version + 1) }),
      })}>重新加载</Button>} />}
    {!!scopeIssues.length && <Alert className="mb-4" type="warning" showIcon
      title="存在无法保存的数据范围" description={scopeIssues.slice(0, 3).join("；")} />}
    {!!riskIssues.length && <Alert className="mb-4" type="warning" showIcon
      title="高风险权限需要有效期限" description={riskIssues.slice(0, 3).join("；")} />}
    <ConfigProvider componentDisabled={loading || saving || previewing || result?.role_id !== roleId}>
    <div className="mb-4 overflow-x-auto"><Segmented value={moduleCode} onChange={(value) => setModuleCode(String(value))}
      options={modules.map((code) => ({ value: code, label: getPermissionModuleName(code) }))} /></div>
    <Space wrap className="mb-4">
      <Checkbox checked={authorizedOnly} onChange={(event) => setAuthorizedOnly(event.target.checked)}>只看已授权页面</Checkbox>
      <Checkbox checked={sensitiveOnly} onChange={(event) => setSensitiveOnly(event.target.checked)}>只看含高风险操作的页面</Checkbox>
      <Input.Search allowClear className="max-w-64" placeholder="搜索页面名称或权限键" value={search}
        aria-label="搜索角色页面权限" onChange={(event) => setSearch(event.target.value)} />
      <Typography.Text type="secondary">批量调整当前筛选 {visibleDefinitions.length} 个页面：</Typography.Text>
      {pagePermissionTierOptions.map(({ value, label }) => <Button key={value} size="small"
        danger={value === 'none'} onClick={() => setVisiblePermission(value)}>
        {label}
      </Button>)}
      <Button size="small" onClick={() => updateVisibleSensitiveActions("renew")}>高风险续期 30 天</Button>
      <Button size="small" danger onClick={() => updateVisibleSensitiveActions("revoke")}>撤销高风险权限</Button>
    </Space>
    <div className="mb-3 flex flex-wrap items-center gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2">
      <Typography.Text type={changes.length ? "warning" : "secondary"}>未保存调整 {changes.length} 个页面</Typography.Text>
      <Typography.Text type="secondary">批量操作只影响当前筛选结果，筛选外页面保持不变。</Typography.Text>
    </div>
    <div className="mb-3 flex flex-wrap items-center gap-3">
      <Button size="small" onClick={() => setExpandedKeys(allGroupKeys(tree))}>展开全部菜单</Button>
      <Button size="small" onClick={() => setExpandedKeys([])}>折叠全部菜单</Button>
      <Typography.Text type="secondary">父级勾选或取消会递归应用到全部下级（含筛选隐藏项）；附加高风险操作需逐项授权并设置期限。</Typography.Text>
    </div>
    <Table<PermissionTreeNode> rowKey="page_key" dataSource={definitions} pagination={false} size="small"
      virtual scroll={{ x: 980, y: 520 }} locale={{ emptyText: search.trim() ? "当前筛选没有匹配页面" : authorizedOnly ? "当前模块没有已授权页面" : "当前模块暂无可配置页面" }}
      columns={([
        { title: "菜单页面", key: "page_name", width: 420, render: (_, node) => <span>
          <Typography.Text strong={Boolean(node.children?.length)}>{node.page_name}</Typography.Text>
          {node.pageKeys.some((key) => changedPageKeys.has(key)) && <Tag color="orange" className="ml-2">未保存</Tag>}
          {node.children?.length ? <Typography.Text type="secondary" className="ml-2">{node.pageKeys.length} 个页面</Typography.Text> : null}
          {node.definition && <Typography.Text type="secondary" className="ml-2 text-xs">{node.page_key}</Typography.Text>}
          {!!node.definition?.sensitive_actions?.length && <div className="ml-6 my-2">
            <Space wrap size={6}>
              <Typography.Text strong>附加高风险操作</Typography.Text>
              <Tag color="orange">依赖普通操作</Tag>
              <Typography.Text type="secondary">已选 {editable[node.page_key]?.sensitiveActions.length || 0}/{node.definition.sensitive_actions.length}</Typography.Text>
            </Space>
            <Typography.Text type="secondary" className="block text-xs">勾选后自动启用普通操作；取消普通操作会同时撤销这些权限。</Typography.Text>
            <Checkbox.Group className="mt-2" value={editable[node.page_key]?.sensitiveActions || []}
              onChange={(values) => update(node.page_key, {
                sensitiveActions: values as string[],
                sensitiveActionsExpiresAt: values.length ? editable[node.page_key]?.sensitiveActionsExpiresAt || null : null,
                permissions: values.length ? normalize(["operate"]) : editable[node.page_key]?.permissions || [],
              })}><Space orientation="vertical">{node.definition.sensitive_actions.map((action) => <Checkbox key={action.key} value={action.key}
                title={action.description}>{action.name}</Checkbox>)}</Space></Checkbox.Group>
            {!!editable[node.page_key]?.sensitiveActions.length && <SensitiveActionExpiryEditor
              value={editable[node.page_key]?.sensitiveActionsExpiresAt}
              onChange={(value) => update(node.page_key, { sensitiveActionsExpiresAt: value })}
              onRevoke={() => update(node.page_key, {
                sensitiveActions: [], sensitiveActionsExpiresAt: null,
              })} />}
          </div>}
        </span> },
        { title: "权限档位", key: "permissions", width: 360, render: (_, node) => {
          const tiers = new Set(node.pageKeys.map((key) => pagePermissionTier(editable[key]?.permissions || [])))
          const value = tiers.size === 1 ? [...tiers][0] : undefined
          return <Space wrap>
            <Radio.Group size="small" optionType="button" buttonStyle="solid" value={value}
              aria-label="权限档位" data-page-name={node.page_name}
              options={pagePermissionTierOptions.map(({ value: optionValue, label, description }) => ({
                value: optionValue, label, title: description,
              }))}
              onChange={(event) => setEditable((current) => Object.fromEntries(Object.entries(current).map(([key, grant]) => {
                if (!node.pageKeys.includes(key)) return [key, grant]
                const permissions = permissionsForTier(event.target.value as PagePermissionTier)
                return [key, { ...grant, permissions,
                  sensitiveActions: permissions.includes("operate") ? grant.sensitiveActions : [] }]
              })))} />
            {!value && <Tag color="warning">混合档位</Tag>}
          </Space>
        } },
        { title: "基线状态", key: "effective", width: 110, render: (_, node) => {
          const labels = new Set(node.pageKeys.map((key) => pagePermissionTierLabel(editable[key]?.permissions || [])))
          return labels.size === 1 ? <Tag color={[...labels][0] === "无权限" ? "default" : "success"}>{[...labels][0]}</Tag>
            : <Tag color="warning">混合档位</Tag>
        } },
        { title: "数据范围", key: "scope", render: (_, node) => {
          const definition = node.definition
          if (!definition) return null
          const state = editable[definition.page_key]
          if (!PAGE_DATA_SCOPE_VISIBLE) return <Tag>{pageScopeSummary(
            state?.scopeType || "all", state?.departmentIds || [],
            new Map(departments.map((department) => [department.feishu_department_id, department.name])), definition.page_key,
          )}</Tag>
          return <div className="flex gap-2"><Select className="min-w-40" value={state?.scopeType}
            disabled={(!state?.permissions.length && !state?.sensitiveActions.length) ||
              definition.supported_scope_types?.[0] === "not_applicable"}
            options={(definition.supported_scope_types || []).map((value) => ({ value, label: value === "all" && definition.page_key === "production:overview" ? "全部生产数据" : scopeNames[value] || value }))}
            onChange={(scopeType) => update(definition.page_key, { scopeType, departmentIds: [] })} />
            {state?.scopeType === "departments" && <Select mode="multiple" className="min-w-56"
              value={state.departmentIds} options={departments.map((department) => ({
                value: department.feishu_department_id, label: department.name,
              }))} status={pageScopeIssue(state.scopeType, state.departmentIds,
                definition.supported_scope_types || [], activeDepartmentIds) ? "error" : undefined}
              onChange={(departmentIds) => update(definition.page_key, { departmentIds })} />}</div>
        } },
      ] satisfies ColumnsType<PermissionTreeNode>)}
      expandable={{ expandedRowKeys: expandedKeys, indentSize: 24,
        onExpandedRowsChange: (keys) => setExpandedKeys(keys.map(String)) }} />
    </ConfigProvider>
    {role && result && <PagePermissionHistoryDrawer targetType="role" targetId={role.id}
      targetName={role.name} grantVersion={result.grant_version} open={historyOpen}
      onClose={() => setHistoryOpen(false)} onRolledBack={() => {
        setLoading(true); setRefreshVersion((version) => version + 1)
      }} />}
  </Drawer>
}
