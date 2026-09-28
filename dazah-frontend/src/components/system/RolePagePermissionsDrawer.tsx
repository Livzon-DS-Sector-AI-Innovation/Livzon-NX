"use client"

import { useDeferredValue, useEffect, useMemo, useRef, useState, type CSSProperties } from "react"
import { App, Button, Checkbox, ConfigProvider, Drawer, Dropdown, Input, Radio, Segmented, Select, Space, Table, Tag, Tooltip, Typography, theme } from "antd"
import { CloseOutlined, DownOutlined, EyeOutlined, FileTextOutlined, FolderFilled, HistoryOutlined, InfoCircleOutlined, RightOutlined, SearchOutlined, UpOutlined, WarningOutlined } from "@ant-design/icons"
import Alert from "@/components/shared/PlatformNotice"
import {
  getRolePagePermissions,
  previewRolePagePermissions,
  replaceRolePagePermissions,
  type RolePagePermissionsOut,
} from "@/actions/admin"
import type { RoleItem } from "@/lib/api/client/admin"
import type { DepartmentItem } from "@/lib/api/server/admin"
import { getPermissionModuleName } from "@/lib/menu-config"
import { PRODUCTION_OVERVIEW_SECTIONS, PRODUCTION_OVERVIEW_SECTION_KEYS } from "@/lib/production-overview-sections"
import {
  PAGE_DATA_SCOPE_VISIBLE, pageGrantChanges, pagePermissionTier, pagePermissionTierLabel,
  pagePermissionTierOptions, pageScopeIssue, pageScopeSummary, permissionsForTier, type PagePermissionTier,
} from "@/lib/page-permission-editor"
import type { ColumnsType } from "antd/es/table"
import { buildPermissionTree, filterAuthorizedTree, type PermissionTreeNode } from "./rolePagePermissionTree"
import { PagePermissionDiff } from "@/components/shared/PagePermissionDiff"
import { PagePermissionHistoryDrawer } from "@/components/shared/PagePermissionHistoryDrawer"
import styles from "./RolePagePermissionsDrawer.module.css"

type Level = "access" | "query" | "operate"
type Grant = {
  permissions: Level[]
  sensitiveActions: string[]
  scopeType: "not_applicable" | "department_tree" | "departments" | "all" | "self" | "production_fermentation" | "production_extraction"
  departmentIds: string[]
  visibleSections: string[] | null
}
type PermissionRow = PermissionTreeNode & { depth: number; details?: boolean; canExpand?: boolean }
const hasDetails = (node: PermissionTreeNode) => node.page_key === "production:overview" || !!node.definition?.sensitive_actions?.length
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
      visibleSections: grant?.visible_sections ?? null,
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
  const { token } = theme.useToken()
  const editorStyle = {
    "--editor-primary": token.colorPrimary,
    "--editor-primary-bg": token.colorPrimaryBg,
    "--editor-primary-border": token.colorPrimaryBorder,
    "--editor-surface": token.colorFillAlter,
    "--editor-border": token.colorBorderSecondary,
    "--editor-radius": `${token.borderRadius}px`,
    "--editor-radius-lg": `${token.borderRadiusLG}px`,
  } as CSSProperties
  const tableArea = useRef<HTMLDivElement>(null)
  const [tableHeight, setTableHeight] = useState(400)
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
  const [pendingAction, setPendingAction] = useState<"preview" | "save" | null>(null)
  const previewing = pendingAction !== null
  const controlsDisabled = loading || saving || previewing || result?.role_id !== roleId
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
      setPendingAction(null)
      savingVersion.current = null
      setResult(null)
      setReason("")
      setErrorMessage("")
      void getRolePagePermissions(roleId).then((next) => {
        if (version !== loadVersion.current) return
        if (next.role_id !== roleId) throw new Error("角色授权返回对象不一致，请重新加载")
        setResult(next)
        setEditable(editableState(next))
        setExpandedKeys((next.definitions || []).filter((definition) =>
          definition.page_key === "production:overview" || definition.sensitive_actions?.length).map((definition) => definition.page_key))
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

  useEffect(() => {
    const element = tableArea.current
    if (!open || loading || !element || typeof ResizeObserver === "undefined") return
    const observer = new ResizeObserver(() => setTableHeight(Math.max(180, element.clientHeight - 66)))
    observer.observe(element)
    return () => observer.disconnect()
  }, [open, loading])

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
  const allGroupKeys = (nodes: PermissionTreeNode[]): string[] => nodes.flatMap((node) => [
    ...(node.children?.length || hasDetails(node) ? [node.page_key] : []), ...allGroupKeys(node.children || []),
  ])
  // Detail rows span the full virtual table, keeping both panels out of the menu-name column.
  const rows: PermissionRow[] = []
  const appendRows = (nodes: PermissionTreeNode[], depth = 0) => nodes.forEach((node) => {
    rows.push({ ...node, children: undefined, depth, canExpand: !!node.children?.length || hasDetails(node) })
    if (!expandedKeys.includes(node.page_key)) return
    if (hasDetails(node)) rows.push({ ...node, children: undefined, depth, details: true })
    appendRows(node.children || [], depth + 1)
  })
  appendRows(definitions)
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
  const inCurrentSession = (action: () => void | Promise<void>) => {
    const version = loadVersion.current
    return () => { if (version === loadVersion.current) return action() }
  }
  const close = () => {
    if (!changes.length) return onClose()
    modal.confirm({ centered: true, title: "放弃未保存的角色授权？", content: "当前更改尚未保存，继续后将丢失。",
      okText: "放弃更改", cancelText: "继续编辑", onOk: inCurrentSession(onClose) })
  }
  const roleGrants = () => Object.entries(editable).flatMap(([pageKey, grant]) =>
    grant.permissions.length || grant.sensitiveActions.length ? [{
      page_key: pageKey,
      mode: "custom" as const,
      permissions: grant.permissions,
      sensitive_actions: grant.sensitiveActions,
      visible_sections: grant.visibleSections,
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

  const previewChanges = async (action: "preview" | "save") => {
    if (!open || loading || saving || previewing || !role || !result || result.role_id !== role.id) return
    if (action === "save" && !reason.trim()) { message.warning("请填写本次角色授权调整原因"); return }
    if (!changes.length) { message.info("没有需要预览或保存的权限调整"); return }
    if (scopeIssues.length) { message.error(scopeIssues[0]); return }
    const version = loadVersion.current
    const idempotencyKey = crypto.randomUUID()
    if (action === "save") pendingIdempotencyKey.current = idempotencyKey
    setPendingAction(action)
    try {
      const impact = await previewRolePagePermissions(role.id, {
        expected_grant_version: result.grant_version,
        grants: roleGrants(),
        reason: reason.trim() || "预览角色页面权限",
        idempotency_key: idempotencyKey,
      })
      if (version !== loadVersion.current) return
      const content = <div className="space-y-3">
        <PagePermissionDiff changes={changes} />
        <div className="space-y-1">
          <div>角色成员 {impact.member_count} 人，实际权限会变化 {impact.affected_user_count} 人：</div>
          <div>权限扩大 {impact.expanded_user_count} 人；权限收紧 {impact.restricted_user_count} 人；混合变化 {impact.mixed_user_count} 人。</div>
          <div>其中 {impact.users_with_overrides} 人在本次变化涉及的页面设置了用户覆盖，最终结果已按覆盖优先计算。</div>
          {!!impact.affected_user_samples?.length && <div>影响样例：{impact.affected_user_samples.map((item) => item.user_name).join("、")}</div>}
        </div>
      </div>
      if (action === "preview") {
        modal.info({ title: `${role.name}的页面权限预览`, width: 960, content, okText: "返回修改" })
        return
      }
      modal.confirm({ centered: true, title: `确认调整${role.name}的页面权限`, width: 960, content,
        okText: "确认保存", cancelText: "返回修改",
        onOk: inCurrentSession(save), onCancel: () => { pendingIdempotencyKey.current = null } })
    } catch (error) {
      if (version === loadVersion.current) setErrorMessage(error instanceof Error ? error.message : "角色授权影响预演失败")
    } finally {
      if (version === loadVersion.current) setPendingAction(null)
    }
  }

  const setVisiblePermission = (tier: PagePermissionTier) => {
    const targetKeys = visibleDefinitions.map((definition) => definition.page_key)
    if (!targetKeys.length) { message.info("当前筛选没有可调整的页面"); return }
    modal.confirm({
      centered: true,
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

  const revokeVisibleSensitiveActions = () => {
    const targetKeys = visibleDefinitions.map((item) => item.page_key)
      .filter((pageKey) => editable[pageKey]?.sensitiveActions.length)
    if (!targetKeys.length) { message.info("当前筛选没有已授权的高风险动作"); return }
    const verb = "撤销"
    modal.confirm({
      centered: true,
      title: `批量${verb}高风险权限？`,
      content: `将处理当前筛选结果中的 ${targetKeys.length} 个页面。`,
      okText: `确认${verb}`, cancelText: "取消",
      onOk: inCurrentSession(() => {
        setEditable((current) => ({
          ...current,
          ...Object.fromEntries(targetKeys.map((pageKey) => [pageKey, {
            ...current[pageKey],
            sensitiveActions: [],
          }])),
        }))
        message.info(`已${verb} ${targetKeys.length} 个页面的高风险权限，保存后生效`)
      }),
    })
  }

  return <Drawer open={open} onClose={close} placement="right" size="min(1360px, 92vw)" mask={{ closable: true }}
    rootClassName={styles.editor} rootStyle={editorStyle} closable={false}
    classNames={{ section: styles.container, header: styles.header, body: styles.body, footer: styles.drawerFooter, mask: styles.mask }}
    title={<div className={styles.heading}>
      <Button type="text" icon={<CloseOutlined />} aria-label="关闭页面权限" onClick={close} />
      <Typography.Title level={3} style={{ margin: 0, fontSize: token.fontSizeXL }}>{role?.name || "角色"} · 页面权限基线</Typography.Title>
      <Button className={styles.historyButton} icon={<HistoryOutlined />} onClick={() => setHistoryOpen(true)} disabled={!result}>授权历史</Button>
    </div>}
    footer={<div className={styles.footer}>
      <Input className={styles.reason} prefix={<FileTextOutlined />} showCount
        aria-label="角色授权调整原因（必填）" disabled={loading || saving || previewing} value={reason}
        onChange={(event) => setReason(event.target.value)} placeholder="填写角色授权调整原因" maxLength={500} />
      <Button className={styles.footerButton} loading={pendingAction === "preview"} onClick={() => void previewChanges("preview")}
        disabled={loading || saving || previewing || !result || result.role_id !== role?.id}>预览</Button>
      <Button className={styles.footerButton} type="primary" loading={saving || pendingAction === "save"} onClick={() => void previewChanges("save")}
        disabled={loading || saving || previewing || !result || result.role_id !== role?.id}>保存</Button>
    </div>}>
    <Alert className={styles.rulesNotice} title="模块入口随有效页面访问权限自动生效；高风险授权依赖普通操作。"
      description="保存角色页面权限后，成员的模块入口按多个角色与用户页面覆盖的最终结果自动计算，无需单独开通模块。模块内至少一个页面可访问时开通入口；撤销最后一个可访问页面后关闭入口。用户有精确覆盖时，以用户覆盖为准。系统管理员默认拥有全部模块访问权限。高风险操作是“普通操作”之上的附加授权，勾选时会自动启用普通操作，取消普通操作时会一并撤销。" />
    {errorMessage && <Alert className="mb-4" type="error" showIcon title={errorMessage}
      action={<Button size="small" onClick={() => modal.confirm({ centered: true, title: "重新加载最新角色授权？",
        content: "刷新会放弃未保存的本地调整，请先核对需要保留的更改。", okText: "重新加载", cancelText: "继续编辑",
        onOk: inCurrentSession(() => { setLoading(true); setRefreshVersion((version) => version + 1) }),
      })}>重新加载</Button>} />}
    {!!scopeIssues.length && <Alert className="mb-4" type="warning" showIcon
      title="存在无法保存的数据范围" description={scopeIssues.slice(0, 3).join("；")} />}
    <ConfigProvider componentDisabled={controlsDisabled}>
    <div className={styles.moduleNavigation}><Segmented className={styles.modules} value={moduleCode}
      aria-label="业务模块" onChange={(value) => setModuleCode(String(value))}
      options={modules.map((code) => ({ value: code, label: getPermissionModuleName(code) }))} /></div>
    <div className={styles.toolbar}>
      <div className={styles.filters}>
        <Checkbox checked={authorizedOnly} onChange={(event) => setAuthorizedOnly(event.target.checked)}>只看已授权页面</Checkbox>
        <Checkbox checked={sensitiveOnly} onChange={(event) => setSensitiveOnly(event.target.checked)}>只看含高风险操作的页面</Checkbox>
        <Input allowClear className={styles.search} prefix={<SearchOutlined />} placeholder="搜索页面名称或权限键" value={search}
          aria-label="搜索角色页面权限" onChange={(event) => setSearch(event.target.value)} />
      </div>
      <div className={styles.batchActions}>
        <Typography.Text type="secondary">批量调整当前筛选 {visibleDefinitions.length} 个页面：</Typography.Text>
        {pagePermissionTierOptions.filter(({ value }) => value !== "operate").map(({ value, label }) =>
          <Button key={value} className={value === "none" ? styles.clearButton : undefined}
            disabled={controlsDisabled || !visibleDefinitions.length} onClick={() => setVisiblePermission(value)}>{label}</Button>)}
        <Space.Compact className={styles.batchDropdown}>
          <Button disabled={controlsDisabled || !visibleDefinitions.length} onClick={() => setVisiblePermission("operate")}>普通操作</Button>
          <Dropdown disabled={controlsDisabled || !visibleDefinitions.length} menu={{ items: [
            { key: "revoke", label: "撤销高风险权限", danger: true, onClick: revokeVisibleSensitiveActions },
          ] }}>
            <Button aria-label="更多批量权限操作" icon={<DownOutlined />} disabled={controlsDisabled || !visibleDefinitions.length} />
          </Dropdown>
        </Space.Compact>
      </div>
    </div>
    <Alert className={styles.changesNotice} type={changes.length ? "warning" : "info"}
      title={`未保存调整 ${changes.length} 个页面，批量操作只影响当前筛选结果，筛选外页面保持不变。`}
      description="批量操作仅调整当前模块的筛选结果；所有更改在填写调整原因、预览影响并确认保存后生效。" />
    <div className={styles.treeToolbar}>
      <Button size="small" icon={<DownOutlined />} iconPlacement="end" onClick={() => setExpandedKeys(allGroupKeys(tree))}>展开全部菜单</Button>
      <Button size="small" icon={<UpOutlined />} iconPlacement="end" onClick={() => setExpandedKeys([])}>折叠全部菜单</Button>
      <Typography.Text type="secondary">父级勾选或取消会递归应用到全部下级（含筛选隐藏项）；附加高风险操作需逐项授权。</Typography.Text>
    </div>
    <div ref={tableArea} className={styles.tableArea}>
    <Table<PermissionRow> className={styles.permissionTable} rowKey={(node) => `${node.page_key}${node.details ? ":details" : ""}`}
      dataSource={rows} loading={loading} pagination={false} size="small" rowClassName={(node) => node.details ? styles.detailsRow : styles.menuRow}
      virtual scroll={{ x: 1080, y: tableHeight }} locale={{ emptyText: search.trim() ? "当前筛选没有匹配页面" : authorizedOnly ? "当前模块没有已授权页面" : "当前模块暂无可配置页面" }}
      columns={([
        { title: "菜单页面", key: "page_name", width: 400,
          onCell: (node) => ({ colSpan: node.details ? 4 : 1 }), render: (_, node) => node.details ? <div className={styles.detailPanels}>
          {node.page_key === 'production:overview' && <section className={styles.detailPanel} aria-label="页面内可见项">
            <div className={styles.panelHeading}><span className={styles.panelIcon}><EyeOutlined /></span><Typography.Text strong>页面内可见项</Typography.Text></div>
            <Typography.Text type="secondary" className="block text-xs">产品勾选同时控制汇总数据；产销计划单独控制。</Typography.Text>
            <Checkbox.Group className={styles.visibleSections} value={editable[node.page_key]?.visibleSections ?? PRODUCTION_OVERVIEW_SECTION_KEYS}
              disabled={controlsDisabled || !editable[node.page_key]?.permissions.includes('query')}
              onChange={(values) => update(node.page_key, { visibleSections:
                values.length === PRODUCTION_OVERVIEW_SECTION_KEYS.length ? null : values as string[] })}>
              {PRODUCTION_OVERVIEW_SECTIONS.map((section) => <Checkbox key={section.key} value={section.key}>{section.label}</Checkbox>)}
            </Checkbox.Group>
          </section>}
          {!!node.definition?.sensitive_actions?.length && <section className={styles.detailPanel} aria-label="附加高风险操作">
            <div className={styles.panelHeading}>
              <span className={styles.panelIcon}><WarningOutlined /></span><Typography.Text strong>附加高风险操作</Typography.Text>
              <Tag color="orange">依赖普通操作</Tag>
              <Typography.Text className={styles.selectedCount} type="secondary">已选 {editable[node.page_key]?.sensitiveActions.length || 0}/{node.definition.sensitive_actions.length}</Typography.Text>
            </div>
            <Typography.Text type="secondary" className="block text-xs">勾选后自动启用普通操作；取消普通操作会同时撤销这些权限。</Typography.Text>
            <Checkbox.Group className={styles.sensitiveActions} value={editable[node.page_key]?.sensitiveActions || []}
              onChange={(values) => update(node.page_key, {
                sensitiveActions: values as string[],
                permissions: values.length ? normalize(["operate"]) : editable[node.page_key]?.permissions || [],
              })}>{node.definition.sensitive_actions.map((action) => <Checkbox key={action.key} value={action.key} aria-label={action.name}>
                <span className={styles.actionName}>{action.name}</span>
                {action.description && <Typography.Text type="secondary" className={styles.actionDescription}>{action.description}</Typography.Text>}
              </Checkbox>)}</Checkbox.Group>
          </section>}
        </div> : <div className={styles.menuIdentity} style={{ paddingInlineStart: node.depth * 24 }}>
          {node.canExpand ? <Button className={styles.expandButton} size="small"
            aria-label={`${expandedKeys.includes(node.page_key) ? "折叠" : "展开"}${node.page_name}`}
            aria-expanded={expandedKeys.includes(node.page_key)} icon={expandedKeys.includes(node.page_key) ? <DownOutlined /> : <RightOutlined />}
            onClick={() => setExpandedKeys((current) => current.includes(node.page_key)
              ? current.filter((key) => key !== node.page_key) : [...current, node.page_key])} /> : <span className={styles.expandPlaceholder} />}
          <FolderFilled className={styles.folderIcon} aria-hidden />
          <div className={styles.pageContent}>
            <div className={styles.pageHeader}>
              <Typography.Title level={4} className={styles.pageTitle} style={{ margin: 0, fontSize: 15, lineHeight: token.lineHeightLG }}>{node.page_name}</Typography.Title>
              {node.pageKeys.some((key) => changedPageKeys.has(key)) && <Tag color="orange">未保存</Tag>}
              {!node.definition && <Typography.Text type="secondary">{node.pageKeys.length} 个页面</Typography.Text>}
            </div>
            {node.definition && <Typography.Text type="secondary" className={styles.pageKey} style={{ fontSize: token.fontSizeSM }}>{node.page_key}</Typography.Text>}
          </div>
        </div> },
        { title: "权限档位", key: "permissions", width: 340, onCell: (node) => ({ colSpan: node.details ? 0 : 1 }), render: (_, node) => {
          if (node.details) return null
          const tiers = new Set(node.pageKeys.map((key) => pagePermissionTier(editable[key]?.permissions || [])))
          const value = tiers.size === 1 ? [...tiers][0] : undefined
          return <Space wrap>
            <Radio.Group className={styles.tiers} optionType="button" value={value}
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
        { title: "基线状态", key: "effective", width: 120, onCell: (node) => ({ colSpan: node.details ? 0 : 1 }), render: (_, node) => {
          if (node.details) return null
          const labels = new Set(node.pageKeys.map((key) => pagePermissionTierLabel(editable[key]?.permissions || [])))
          return labels.size === 1 ? <Tag color={[...labels][0] === "无权限" ? "default" : "success"}>{[...labels][0]}</Tag>
            : <Tag color="warning">混合档位</Tag>
        } },
        { title: <Space size={6}>数据范围<Tooltip title="数据范围决定授权页面可查询的数据；指定部门时必须选择有效部门。"><InfoCircleOutlined tabIndex={0} /></Tooltip></Space>,
          key: "scope", width: 220, onHeaderCell: () => ({ "aria-label": "数据范围" }),
          onCell: (node) => ({ colSpan: node.details ? 0 : 1 }), render: (_, node) => {
          if (node.details) return null
          const definition = node.definition
          if (!definition) return null
          const state = editable[definition.page_key]
          if (!PAGE_DATA_SCOPE_VISIBLE) return <Tag>{pageScopeSummary(
            state?.scopeType || "all", state?.departmentIds || [],
            new Map(departments.map((department) => [department.feishu_department_id, department.name])), definition.page_key,
          )}</Tag>
          return <div className={styles.scopeControls}><Select aria-label={`${node.page_name}数据范围`} value={state?.scopeType}
            disabled={controlsDisabled || (!state?.permissions.length && !state?.sensitiveActions.length) ||
              definition.supported_scope_types?.[0] === "not_applicable"}
            options={(definition.supported_scope_types || []).map((value) => ({ value, label: value === "all" && definition.page_key === "production:overview" ? "全部生产数据" : scopeNames[value] || value }))}
            onChange={(scopeType) => update(definition.page_key, { scopeType, departmentIds: [] })} />
            {state?.scopeType === "departments" && <Select mode="multiple" aria-label={`${node.page_name}指定部门`}
              value={state.departmentIds} options={departments.map((department) => ({
                value: department.feishu_department_id, label: department.name,
              }))} status={pageScopeIssue(state.scopeType, state.departmentIds,
                definition.supported_scope_types || [], activeDepartmentIds) ? "error" : undefined}
              onChange={(departmentIds) => update(definition.page_key, { departmentIds })} />}</div>
        } },
      ] satisfies ColumnsType<PermissionRow>)} />
    </div>
    </ConfigProvider>
    {role && result && <PagePermissionHistoryDrawer targetType="role" targetId={role.id}
      targetName={role.name} grantVersion={result.grant_version} open={historyOpen}
      onClose={() => setHistoryOpen(false)} onRolledBack={() => {
        setLoading(true); setRefreshVersion((version) => version + 1)
      }} />}
  </Drawer>
}
