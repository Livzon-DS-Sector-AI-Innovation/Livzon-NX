"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import dynamic from "next/dynamic"
import { App, Button, Checkbox, ConfigProvider, Dropdown, Empty, Input, Radio, Select, Spin, Tag, type InputRef } from "antd"
import { AppstoreOutlined, BlockOutlined, CheckCircleFilled, DatabaseOutlined, DownOutlined, FileTextOutlined, FolderFilled, HistoryOutlined, LeftOutlined, RightOutlined, SearchOutlined, SwapOutlined, TeamOutlined, UpOutlined, WarningOutlined } from "@ant-design/icons"
import PlatformNotice from "@/components/shared/PlatformNotice"
import {
  getRolePagePermissions,
  previewRolePagePermissions,
  replaceRolePagePermissions,
  type RolePagePermissionsOut,
} from "@/actions/admin"
import type { RoleItem } from "@/lib/api/client/admin"
import type { DepartmentItem } from "@/lib/api/server/admin"
import { getPermissionModuleName } from "@/lib/menu-config"
import { productionPageSections } from "@/lib/production-overview-sections"
import {
  pageGrantChanges, pagePermissionTier, pagePermissionTierLabel,
  pagePermissionTierOptions, pageScopeIssue, pageScopeSummary, permissionsForTier, type PagePermissionTier,
} from "@/lib/page-permission-editor"
import { buildPermissionTree, type PermissionTreeNode } from "./rolePagePermissionTree"
import { PagePermissionDiff } from "@/components/shared/PagePermissionDiff"
import { useRouter } from "next/navigation"
import { rolePagePermissionsPath, type PermissionWorkbenchOrigin } from "@/lib/rolePagePermissionsPath"
import styles from "./RolePagePermissionsWorkbench.module.css"

const PagePermissionHistoryDrawer = dynamic(() => import("@/components/shared/PagePermissionHistoryDrawer")
  .then((module) => module.PagePermissionHistoryDrawer))

type InitialLoad = { ok: true; data: RolePagePermissionsOut } | { ok: false; message: string }
const mismatchedRoleMessage = "角色授权返回对象不一致，请重新加载"

type Level = "access" | "query" | "operate"
type Grant = {
  permissions: Level[]
  sensitiveActions: string[]
  scopeType: "not_applicable" | "department_tree" | "departments" | "all" | "self" | "production_fermentation" | "production_extraction"
  departmentIds: string[]
  visibleSections: string[] | null
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
      visibleSections: grant?.visible_sections ?? null,
    }]
  }))
}

function flattenGroups(node: PermissionTreeNode): PermissionTreeNode[] {
  return node.children?.length ? [node, ...node.children.flatMap(flattenGroups)] : []
}

export function RolePagePermissionsRoute({ role, roles, departments, origin, initialPageKey, initialLoad }: {
  role: RoleItem
  roles: RoleItem[]
  departments: DepartmentItem[]
  origin: PermissionWorkbenchOrigin
  initialPageKey?: string
  initialLoad: InitialLoad
}) {
  const router = useRouter()
  const returnTo = origin === "settings" ? "/settings?tab=permissions"
    : origin === "health" ? "/system/permission-verification" : "/system/roles"

  return <RolePagePermissionsWorkbench key={`${role.id}:${initialPageKey ?? ""}`} role={role} roles={roles} departments={departments}
    initialPageKey={initialPageKey} initialLoad={initialLoad} onClose={() => router.push(returnTo)}
    onRoleChange={(id) => router.push(rolePagePermissionsPath(id, origin))} />
}

export function RolePagePermissionsWorkbench({ role, roles, departments, onClose, onRoleChange, initialPageKey, initialLoad }: {
  role: RoleItem
  roles?: RoleItem[]
  departments: DepartmentItem[]
  onClose: () => void
  onRoleChange?: (id: string) => void
  initialPageKey?: string
  initialLoad?: InitialLoad
}) {
  const { message, modal } = App.useApp()
  const searchInput = useRef<InputRef>(null)
  const loadVersion = useRef(0)
  const savingVersion = useRef<number | null>(null)
  const pendingIdempotencyKey = useRef<string | null>(null)
  const roleId = role.id
  const hasInitialLoad = initialLoad !== undefined
  const [initialResult] = useState(() => initialLoad?.ok && initialLoad.data.role_id === roleId ? initialLoad.data : null)
  const [initialDefinition] = useState(() => initialResult?.definitions?.find((definition) => definition.page_key === initialPageKey))
  const [result, setResult] = useState<RolePagePermissionsOut | null>(initialResult)
  const [editable, setEditable] = useState<Record<string, Grant>>(() => initialResult ? editableState(initialResult) : {})
  const [moduleCode, setModuleCode] = useState(initialDefinition?.module_code ?? initialResult?.definitions?.[0]?.module_code ?? "")
  const [reason, setReason] = useState("")
  const [loading, setLoading] = useState(!hasInitialLoad)
  const [saving, setSaving] = useState(false)
  const [pendingAction, setPendingAction] = useState<"preview" | "save" | null>(null)
  const previewing = pendingAction !== null
  const savePending = saving || pendingAction === "save"
  const controlsDisabled = loading || saving || previewing || result?.role_id !== roleId
  const [errorMessage, setErrorMessage] = useState(() => initialLoad?.ok === false ? initialLoad.message
    : initialLoad && !initialResult ? mismatchedRoleMessage : "")
  const [refreshVersion, setRefreshVersion] = useState(0)
  const [authorizedOnly, setAuthorizedOnly] = useState(false)
  const [sensitiveOnly, setSensitiveOnly] = useState(false)
  const [search, setSearch] = useState("")
  const [tierFilter, setTierFilter] = useState<PagePermissionTier | "all">("all")
  const [riskFilter, setRiskFilter] = useState("all")
  const [scopeFilter, setScopeFilter] = useState("any")
  const [groupKey, setGroupKey] = useState<string>()
  const [pageKey, setPageKey] = useState(initialDefinition?.page_key)
  const [collapsedSummaryKey, setCollapsedSummaryKey] = useState<string>()
  const [treeExpansion, setTreeExpansion] = useState<Record<string, boolean>>({})
  const [groupExpansion, setGroupExpansion] = useState<Record<string, boolean>>({})
  const [historyOpen, setHistoryOpen] = useState<boolean>()
  const resetFilters = useCallback(() => {
    setTierFilter("all")
    setRiskFilter("all")
    setScopeFilter("any")
    setAuthorizedOnly(false)
    setSensitiveOnly(false)
    setSearch("")
  }, [])

  useEffect(() => {
    const focusSearch = (event: KeyboardEvent) => {
      const input = searchInput.current?.input
      if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== "k" || !input || input.disabled ||
        (event.target instanceof Element && event.target.closest('[role="dialog"]'))) return
      event.preventDefault()
      input.focus()
    }
    window.addEventListener("keydown", focusSearch)
    return () => window.removeEventListener("keydown", focusSearch)
  }, [])

  useEffect(() => {
    const version = ++loadVersion.current
    if (!hasInitialLoad || refreshVersion > 0) queueMicrotask(() => {
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
        if (next.role_id !== roleId) throw new Error(mismatchedRoleMessage)
        setResult(next)
        setEditable(editableState(next))
        const initial = next.definitions?.find((definition) => definition.page_key === initialPageKey)
        setPageKey(initial?.page_key)
        setCollapsedSummaryKey(undefined)
        setGroupKey(undefined)
        setGroupExpansion({})
        setTreeExpansion({})
        resetFilters()
        setModuleCode(initial?.module_code ?? next.definitions?.[0]?.module_code ?? "")
        setReason("")
        setErrorMessage("")
      }).catch((error) => { if (version === loadVersion.current) setErrorMessage(error instanceof Error ? error.message : "加载角色页面权限失败") })
        .finally(() => { if (version === loadVersion.current) setLoading(false) })
    })
    return () => { loadVersion.current += 1 }
  }, [hasInitialLoad, initialPageKey, resetFilters, roleId, refreshVersion])

  const definitionList = useMemo(() => result?.role_id === roleId ? result.definitions ?? [] : [], [result, roleId])
  const modules = useMemo(() => [...new Set(definitionList.map(({ module_code }) => module_code))], [definitionList])
  const moduleDefinitions = useMemo(() => definitionList.filter((definition) => definition.module_code === moduleCode),
    [definitionList, moduleCode])
  const moduleTree = useMemo(() => buildPermissionTree(moduleDefinitions), [moduleDefinitions])
  const groups = useMemo(() => moduleTree.flatMap(flattenGroups), [moduleTree])
  const group = groups.find((node) => node.page_key === groupKey)
  const groupKeys = useMemo(() => group && new Set(group.pageKeys), [group])
  const keyword = search.trim().toLowerCase()
  const matchesFilters = useCallback((definition: (typeof moduleDefinitions)[number]) => {
    const grant = editable[definition.page_key]
    if (authorizedOnly && !grant?.permissions.length) return false
    if (sensitiveOnly && !definition.sensitive_actions?.length) return false
    if (tierFilter !== "all" && pagePermissionTier(grant?.permissions ?? []) !== tierFilter) return false
    if (scopeFilter !== "any" && grant?.scopeType !== scopeFilter) return false
    if (riskFilter === "granted" && !grant?.sensitiveActions.length) return false
    if (riskFilter === "ungranted" && (!definition.sensitive_actions?.length || grant?.sensitiveActions.length)) return false
    if (!keyword) return true
    const actionTerms = (definition.sensitive_actions ?? []).flatMap((action) => [action.key, action.name, action.description])
    return [definition.page_name, definition.page_key, definition.route_path, ...actionTerms]
      .some((value) => value?.toLowerCase().includes(keyword))
  }, [editable, authorizedOnly, sensitiveOnly, tierFilter, scopeFilter, riskFilter, keyword])
  const hasFilters = Boolean(keyword || authorizedOnly || sensitiveOnly || tierFilter !== "all" ||
    scopeFilter !== "any" || riskFilter !== "all")
  const visibleDefinitions = useMemo(() => !groupKeys && !hasFilters ? moduleDefinitions : moduleDefinitions.filter((definition) =>
    (!groupKeys || groupKeys.has(definition.page_key)) && matchesFilters(definition)),
    [moduleDefinitions, groupKeys, hasFilters, matchesFilters])
  const visibleTree = useMemo(() => visibleDefinitions === moduleDefinitions ? moduleTree : buildPermissionTree(visibleDefinitions),
    [visibleDefinitions, moduleDefinitions, moduleTree])
  const selected = visibleDefinitions.find((definition) => definition.page_key === pageKey) ?? visibleDefinitions[0]
  const selectedGrant = selected && editable[selected.page_key]
  const selectGroup = (nextGroup?: string) => {
    setGroupKey(nextGroup)
    setPageKey(undefined)
    setCollapsedSummaryKey(undefined)
    setGroupExpansion({})
  }
  const selectTreePage = (definition: (typeof moduleDefinitions)[number]) => {
    if (!matchesFilters(definition)) resetFilters()
    if (groupKeys && !groupKeys.has(definition.page_key)) setGroupKey(undefined)
    setGroupExpansion({})
    setPageKey(definition.page_key)
    setCollapsedSummaryKey(undefined)
  }
  const update = (pageKey: string, patch: Partial<Grant>) => setEditable((current) => ({
    ...current, [pageKey]: { ...current[pageKey], ...patch },
  }))
  const departmentNames = useMemo(() => new Map(departments.map((department) => [department.feishu_department_id, department.name])), [departments])
  const baseline = useMemo(() => result ? editableState(result) : {}, [result])
  const changes = useMemo(() => pageGrantChanges(definitionList, baseline, editable, departmentNames),
    [definitionList, baseline, editable, departmentNames])
  const hasChanges = changes.length > 0
  useEffect(() => {
    if (!hasChanges) return
    const preventUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ""
    }
    window.addEventListener("beforeunload", preventUnload)
    return () => window.removeEventListener("beforeunload", preventUnload)
  }, [hasChanges])
  const changedPageKeys = useMemo(() => new Set(changes.map((change) => change.pageKey)), [changes])
  const activeDepartmentIds = useMemo(() => new Set(departmentNames.keys()), [departmentNames])
  const scopeIssues = useMemo(() => definitionList.flatMap((definition) => {
    const grant = editable[definition.page_key]
    if (!grant?.permissions.length && !grant?.sensitiveActions.length) return []
    const issue = pageScopeIssue(grant.scopeType, grant.departmentIds,
      definition.supported_scope_types || [], activeDepartmentIds)
    return issue ? [`${definition.page_name}：${issue}`] : []
  }), [definitionList, editable, activeDepartmentIds])
  const inCurrentSession = (action: () => void | Promise<void>) => {
    const version = loadVersion.current
    return () => { if (version === loadVersion.current) return action() }
  }
  const leave = (navigate: () => void) => {
    if (saving || previewing) return
    if (!hasChanges) return navigate()
    modal.confirm({ centered: true, title: "放弃未保存的角色授权？", content: "当前更改尚未保存，继续后将丢失。",
      okText: "放弃更改", cancelText: "继续编辑", onOk: inCurrentSession(navigate) })
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
    if (!result || result.role_id !== role.id || loading || saving) return
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
    if (loading || saving || previewing || !result || result.role_id !== role.id) return
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

  const setPageTiers = (pageKeys: string[], tier: PagePermissionTier) => {
    const permissions = permissionsForTier(tier)
    setEditable((current) => {
      const next = { ...current }
      for (const key of pageKeys) {
        const grant = current[key]
        if (grant) next[key] = { ...grant, permissions, sensitiveActions: tier === "operate" ? grant.sensitiveActions : [] }
      }
      return next
    })
  }

  const batchScope = `${getPermissionModuleName(moduleCode)}${group ? ` / ${group.page_name}` : ""}的当前筛选结果`
  const setVisiblePermission = (tier: PagePermissionTier) => {
    const targetKeys = visibleDefinitions.map((definition) => definition.page_key)
    if (!targetKeys.length) { message.info("当前筛选没有可调整的页面"); return }
    modal.confirm({
      centered: true,
      title: `批量设为“${pagePermissionTierOptions.find((option) => option.value === tier)?.label}”？`,
      content: `将调整${batchScope}中的 ${targetKeys.length} 个页面。${tier !== "operate" ? "这些页面的附加高风险权限也将撤销。" : "现有高风险授权保留。"}保存后生效。`,
      okText: `调整 ${targetKeys.length} 个页面`, cancelText: "取消",
      onOk: inCurrentSession(() => {
        setPageTiers(targetKeys, tier)
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
      content: `将撤销${batchScope}中 ${targetKeys.length} 个页面的全部高风险授权。保存后生效。`,
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

  const tierControl = (definition: NonNullable<typeof selected>, detail = false) => (
    <Radio.Group className={styles.tiers} size="small" optionType="button" buttonStyle="solid"
      aria-label={detail ? "基础权限" : `${definition.page_name}权限档位`} data-page-name={definition.page_name}
      value={pagePermissionTier(editable[definition.page_key]?.permissions ?? [])}
      options={pagePermissionTierOptions.map(({ value, label, description }) => ({ value, label, title: description }))}
      onChange={(event) => {
        const tier = pagePermissionTierOptions.find(({ value }) => value === event.target.value)?.value
        if (tier) {
          setPageKey(definition.page_key)
          setPageTiers([definition.page_key], tier)
        }
      }} />
  )

  const renderTreePage = (node: PermissionTreeNode) => {
    const children = node.children ?? []
    const isGroup = children.length > 0
    const active = isGroup ? groupKey === node.page_key : selected?.page_key === node.page_key
    const expanded = treeExpansion[node.page_key] ??
      (active || node.pageKeys.includes(selected?.page_key ?? ""))
    const definition = node.definition
    return <li key={node.page_key}>
      <div className={styles.treeRow} data-selected={active}>
        {isGroup ? <button type="button" className={styles.caret} aria-expanded={expanded}
          aria-label={`${expanded ? "折叠" : "展开"}${node.page_name}导航`}
          onClick={() => setTreeExpansion((current) => ({ ...current, [node.page_key]: !expanded }))}>
          {expanded ? <DownOutlined /> : <RightOutlined />}
        </button> : <span className={styles.caretSpace} />}
        <button type="button" className={styles.treeItem} aria-pressed={active} onClick={() => {
          if (isGroup) {
            selectGroup(node.page_key)
            if (!expanded) setTreeExpansion((current) => ({ ...current, [node.page_key]: true }))
          } else if (definition) {
            selectTreePage(definition)
          }
        }}>
          {isGroup ? <FolderFilled aria-hidden /> : <FileTextOutlined aria-hidden />}
          <span>{node.page_name}</span>{isGroup && <small>{node.pageKeys.length}</small>}
        </button>
      </div>
      {expanded && isGroup && <ul>{children.map(renderTreePage)}</ul>}
    </li>
  }

  const renderPageGroup = (node: PermissionTreeNode) => {
    const definition = node.definition
    const grant = definition && editable[definition.page_key]
    const active = selected?.page_key === definition?.page_key && Boolean(definition)
    const risks = definition?.sensitive_actions?.length ?? 0
    const summaryOpen = active && collapsedSummaryKey !== definition?.page_key
    const expanded = groupExpansion[node.page_key] ?? (Boolean(keyword || groupKey ||
      tierFilter !== "all" || riskFilter !== "all" || scopeFilter !== "any" || authorizedOnly || sensitiveOnly) ||
      node.pageKeys.includes(selected?.page_key ?? ""))
    return <div className={styles.pageGroup} key={node.page_key}>
      {node.children?.length ? <button type="button" className={styles.groupHeading} aria-expanded={expanded}
        onClick={() => setGroupExpansion((current) => ({ ...current, [node.page_key]: !expanded }))}>
        {expanded ? <DownOutlined /> : <RightOutlined />}<FolderFilled className={styles.accent} />
        <strong>{node.page_name}</strong><small>（{node.pageKeys.length} 个页面）</small>
      </button> : null}
      {(expanded || !node.children?.length) && <>
        {definition && grant && <article className={styles.pageCard} data-selected={active}>
          <div className={styles.pageRow}>
            <button type="button" className={styles.pageIdentity} aria-pressed={active} onClick={() => {
              setPageKey(definition.page_key)
              setCollapsedSummaryKey(undefined)
              if (window.matchMedia("(max-width: 850px)").matches) {
                document.getElementById("role-page-permission-detail")?.scrollIntoView({ block: "nearest" })
              }
            }}>
              <span className={styles.pageIcon}><FileTextOutlined /></span>
              <span className={styles.pageLabel}>
                <strong>{definition.page_name}</strong>
                <small title={definition.route_path || definition.page_key}>{definition.route_path || definition.page_key}</small>
              </span>
            </button>
            {changedPageKeys.has(definition.page_key) && <Tag className={styles.draftTag} color="warning">未保存</Tag>}
            {tierControl(definition)}
            <button type="button" className={styles.pageArrow}
              aria-label={`${summaryOpen ? "折叠" : "展开"}${definition.page_name}配置摘要`}
              aria-expanded={summaryOpen} onClick={() => {
                setPageKey(definition.page_key)
                setCollapsedSummaryKey(summaryOpen ? definition.page_key : undefined)
              }}>
              {summaryOpen ? <UpOutlined /> : <RightOutlined />}
            </button>
          </div>
          {summaryOpen && <div className={styles.pageSummary}>
            <div>
              <h3><AppstoreOutlined />页面信息</h3>
              <p title={definition.page_key}>{definition.page_key}</p>
            </div>
            <div>
              <h3><BlockOutlined />当前配置</h3>
              <p>基础权限：{pagePermissionTierLabel(grant.permissions)}
                {risks > 0 && <span>高风险操作 {grant.sensitiveActions.length}/{risks}</span>}</p>
              {grant.permissions.length > 0 &&
                <p>数据范围：{pageScopeSummary(grant.scopeType, grant.departmentIds, departmentNames, definition.page_key)}</p>}
            </div>
          </div>}
        </article>}
        {node.children?.length ? <div className={styles.groupPages}>{node.children.map(renderPageGroup)}</div> : null}
      </>}
    </div>
  }

  const selectedActions = selected?.sensitive_actions ?? []
  const selectedScopeTypes = selected?.supported_scope_types ?? []
  const supportsDataScope = selectedScopeTypes.some((value) => value !== "not_applicable")
  const selectedSections = productionPageSections(selected?.page_key)
  const selectedChange = changes.find((change) => change.pageKey === selected?.page_key)
  const configuredCount = definitionList.filter((definition) => editable[definition.page_key]?.permissions.length).length
  const highRiskCount = definitionList.reduce((count, definition) => count + (definition.sensitive_actions?.length ?? 0), 0)
  const moduleName = getPermissionModuleName(moduleCode)
  const selectedGroup = selected && groups
    .filter((node) => node.page_key !== selected.page_key && node.pageKeys.includes(selected.page_key)).at(-1)
  const detailTitle = selected ? `页面权限详情：${selected.page_name}` : "页面权限详情"

  return <div className={`${styles.workbench} ${styles.enter}`}>
    <header className={styles.header}>
      <div className={styles.heading}>
        <Button className={styles.back} type="text" icon={<LeftOutlined />} aria-label="返回权限管理" onClick={() => leave(onClose)}
          disabled={saving || previewing} />
        <span className={styles.headingIcon}><BlockOutlined /></span>
        <h1>页面权限基线配置</h1>
      </div>
      <div className={styles.rolePicker}>
        <TeamOutlined className={styles.accent} />
        <label htmlFor="permission-role">当前角色</label>
        {roles && onRoleChange ? <Select id="permission-role" value={roleId} className={styles.roleSelect} variant="borderless"
          disabled={saving || previewing} showSearch={{ optionFilterProp: "label" }}
          options={roles.map(({ id, name }) => ({ value: id, label: name }))}
          onChange={(id) => leave(() => onRoleChange(id))} /> : <strong id="permission-role">{role.name}</strong>}
      </div>
      <dl className={styles.stats} aria-label="角色页面权限统计">
        {[
          { label: "页面总数", value: definitionList.length, icon: <FileTextOutlined className={styles.info} /> },
          { label: "已配置", value: configuredCount, icon: <CheckCircleFilled className={styles.success} />,
            detail: definitionList.length ? `(${Math.round(configuredCount * 100 / definitionList.length)}%)` : undefined },
          { label: "高风险项", value: highRiskCount, icon: <WarningOutlined className={styles.warning} /> },
          { label: "本次变更", value: changes.length, icon: <SwapOutlined />, detail: result ? "项" : undefined },
        ].map(({ label, value, icon, detail }) => <div key={label} className={styles.stat}>
          <span className={styles.accent} aria-hidden>{icon}</span>
          <div><dt>{label}</dt><dd>{result ? value : "—"}{detail && <small>{detail}</small>}</dd></div>
        </div>)}
      </dl>
    </header>

    <nav className={styles.moduleTabs} aria-label="业务模块">
      {modules.map((code) => <button type="button" key={code} aria-pressed={code === moduleCode}
        onClick={() => { setModuleCode(code); selectGroup() }}>{getPermissionModuleName(code)}</button>)}
    </nav>

    <div className={styles.toolbar}>
      <ConfigProvider componentDisabled={controlsDisabled}>
        <Input ref={searchInput} allowClear className={styles.search} prefix={<SearchOutlined />} aria-label="搜索角色页面权限"
          aria-keyshortcuts="Control+K Meta+K" suffix={<kbd className={styles.shortcut}>Ctrl K</kbd>}
          placeholder="搜索页面名称、路径或权限关键词" value={search} onChange={(event) => setSearch(event.target.value)} />
        <Select aria-label="权限状态筛选" value={tierFilter} onChange={setTierFilter} options={[
          { value: "all", label: "权限状态：全部" },
          ...pagePermissionTierOptions.map(({ value, label }) => ({ value, label: `权限状态：${label}` })),
        ]} />
        <Select aria-label="高风险筛选" value={riskFilter} onChange={setRiskFilter} options={[
          { value: "all", label: "高风险：全部" }, { value: "granted", label: "高风险：已授权" },
          { value: "ungranted", label: "高风险：未授权" },
        ]} />
        <Select aria-label="数据范围筛选" value={scopeFilter} onChange={setScopeFilter} options={[
          { value: "any", label: "数据范围：全部" },
          ...Object.entries(scopeNames).map(([value, label]) => ({ value, label: `数据范围：${label}` })),
        ]} />
        <Checkbox checked={authorizedOnly} onChange={(event) => setAuthorizedOnly(event.target.checked)}>仅看已授权页面</Checkbox>
        <Checkbox checked={sensitiveOnly} onChange={(event) => setSensitiveOnly(event.target.checked)}>仅看含高风险操作的页面</Checkbox>
        <div className={styles.tools}>
          <Dropdown trigger={["click"]} disabled={controlsDisabled || !visibleDefinitions.length} menu={{ items: [
            ...pagePermissionTierOptions.map(({ value, label }) => ({
              key: value, label: `设为${label}`, onClick: () => setVisiblePermission(value),
            })),
            { key: "revoke", label: "撤销高风险权限", danger: true, onClick: revokeVisibleSensitiveActions },
          ] }}>
            <Button className={styles.batch} icon={<BlockOutlined />}
              disabled={controlsDisabled || !visibleDefinitions.length}>批量设置 <DownOutlined /></Button>
          </Dropdown>
          <Button className={styles.history} icon={<HistoryOutlined />} aria-label="授权历史" title="授权历史"
            onClick={() => setHistoryOpen(true)} disabled={controlsDisabled} />
        </div>
      </ConfigProvider>
    </div>

    {errorMessage && <PlatformNotice type="error" showIcon title={errorMessage}
      action={<Button size="small" onClick={() => {
        const reload = () => { setLoading(true); setRefreshVersion((version) => version + 1) }
        if (!hasChanges) { reload(); return }
        modal.confirm({ centered: true, title: "重新加载最新角色授权？",
          content: "重新加载会放弃未保存的权限调整。", okText: "重新加载", cancelText: "继续编辑",
          onOk: inCurrentSession(reload) })
      }}>重新加载</Button>} />}
    {!!scopeIssues.length && <PlatformNotice type="warning" showIcon
      title="存在无法保存的数据范围" description={scopeIssues.slice(0, 3).join("；")} />}

    <ConfigProvider componentDisabled={controlsDisabled}>
      <div className={styles.columns}>
        <nav className={styles.panel} aria-label="页面">
          <h2 className={styles.panelHeading}>页面</h2>
          <ul className={styles.treeScroll}>
            {moduleTree.length > 0 && <li>
              <div className={styles.treeRow}>
                <span className={styles.caretSpace} />
                <button type="button" className={styles.treeItem} aria-pressed={!group} onClick={() => selectGroup()}>
                  <AppstoreOutlined aria-hidden /><span>全部页面</span><small>{moduleDefinitions.length}</small>
                </button>
              </div>
            </li>}
            {moduleTree.map(renderTreePage)}
          </ul>
        </nav>

        <section className={styles.panel} aria-labelledby="role-page-permission-list">
          <h2 id="role-page-permission-list" className={styles.panelHeading}>
            {group?.page_name || (moduleCode && moduleName)}{moduleCode && " · "}页面列表
            <small>{visibleDefinitions.length} 个页面</small>
          </h2>
          <div className={styles.pageScroll}>
            {result && <PlatformNotice className={styles.permissionNotice} type="info" showIcon
              title="模块入口随有效页面访问权限自动生效，高风险授权依赖普通操作。"
              description="角色基线和用户覆盖共同决定成员的有效访问权限。模块内至少一个页面可访问时开通入口，撤销最后一个可访问页面后关闭入口。系统管理员默认拥有全部模块访问权限。批量设置仅处理当前模块或分组中的筛选结果。保存需填写调整原因，并预演和确认影响。" />}
            {loading ? <div className={styles.empty} role="status"><Spin /> 加载页面权限</div>
              : visibleTree.length ? visibleTree.map(renderPageGroup)
              : <Empty className={styles.empty} image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={result ? (moduleDefinitions.length ? "当前筛选没有匹配页面" : "当前模块暂无可配置页面") : "页面权限未加载"} />}
          </div>
        </section>

        <section id="role-page-permission-detail" className={styles.panel} aria-label={detailTitle}>
          <div className={styles.detailHeading}>
            <h2><FileTextOutlined className={styles.accent} />{detailTitle}</h2>
            {selected && <span className={styles.origin}>所属：{moduleName}{selectedGroup && ` / ${selectedGroup.page_name}`}</span>}
          </div>
          {selected && selectedGrant ? <div className={styles.detailScroll} key={selected.page_key}>
            <section className={styles.detailSection} aria-label="基础权限">
              <h3><BlockOutlined />基础权限</h3>
              <p>{pagePermissionTierOptions.find(({ value }) => value === pagePermissionTier(selectedGrant.permissions))?.description}</p>
              {tierControl(selected, true)}
            </section>
            <section className={styles.detailSection} aria-label="附加高风险操作">
              <h3><WarningOutlined className={styles.warning} />附加高风险操作
                <small>（{selectedGrant.sensitiveActions.length}/{selectedActions.length}）</small>
                {selectedActions.length > 0 && <Tag className={styles.riskBadge} color="warning">高风险，谨慎授权</Tag>}</h3>
              {selectedActions.length > 0 ? <>
                <p>高风险授权依赖普通操作，需逐项勾选。降低档位会撤销这些授权。</p>
                <Checkbox.Group className={styles.riskActions} value={selectedGrant.sensitiveActions}
                  disabled={controlsDisabled || !selectedGrant.permissions.includes("operate")}
                  onChange={(sensitiveActions) => update(selected.page_key, { sensitiveActions })}>
                  {selectedActions.map((action) => <Checkbox key={action.key} value={action.key} aria-label={action.name}>
                    <strong>{action.name}</strong>{action.description && <small>{action.description}</small>}
                  </Checkbox>)}
                </Checkbox.Group>
              </> : <p>此页面暂无独立高风险操作。</p>}
            </section>
            <section className={`${styles.detailSection} ${styles.scopeSection}`} aria-label="数据范围">
              <h3><DatabaseOutlined /><label htmlFor="permission-data-scope">数据范围</label></h3>
              <Select id="permission-data-scope" aria-label={`${selected.page_name}数据范围`} value={selectedGrant.scopeType}
                disabled={controlsDisabled || !selectedGrant.permissions.length || !supportsDataScope}
                options={selectedScopeTypes.map((value) => ({
                  value, label: value === "all" && selected.page_key === "production:overview" ? "全部生产数据" : scopeNames[value],
                }))}
                onChange={(scopeType) => update(selected.page_key, { scopeType, departmentIds: [] })} />
              {selectedGrant.scopeType === "departments" && <Select mode="multiple" aria-label={`${selected.page_name}指定部门`}
                disabled={controlsDisabled || !selectedGrant.permissions.length} value={selectedGrant.departmentIds}
                options={departments.map((department) => ({ value: department.feishu_department_id, label: department.name }))}
                onChange={(departmentIds) => update(selected.page_key, { departmentIds })}
                status={pageScopeIssue(selectedGrant.scopeType, selectedGrant.departmentIds,
                  selectedScopeTypes, activeDepartmentIds) ? "error" : undefined} />}
              <p>{!supportsDataScope ? "此页面暂未接入数据范围。"
                : selectedGrant.permissions.length ? "控制用户可查看和操作的数据范围。" : "授予页面入口后可配置数据范围。"}</p>
            </section>
            {selectedSections.length > 0 && <section className={styles.detailSection} aria-label="页面内可见项">
              <h3><FolderFilled />页面内可见项</h3>
              <Checkbox.Group value={selectedGrant.visibleSections ?? selectedSections.map((section) => section.key)}
                disabled={controlsDisabled || !selectedGrant.permissions.includes("query")}
                onChange={(values) => update(selected.page_key, {
                  visibleSections: values.length === selectedSections.length ? null : values,
                })}>
                {selectedSections.map(({ key, label }) => <Checkbox key={key} value={key}>{label}</Checkbox>)}
              </Checkbox.Group>
            </section>}
            <section className={styles.detailSection} aria-label="变更摘要">
              <h3><FileTextOutlined />变更摘要</h3>
              {selectedChange ? <dl className={styles.changeSummary}>
                <dt>修改前</dt><dd>{selectedChange.before}</dd>
                <dt>修改后</dt><dd>{selectedChange.after}</dd>
              </dl> : <p>当前页面暂无变更。</p>}
            </section>
          </div> : <Empty className={styles.empty} image={Empty.PRESENTED_IMAGE_SIMPLE} description="请选择要配置的页面" />}
        </section>
      </div>
    </ConfigProvider>

    <footer className={styles.footer}>
      <span className={styles.draftStatus} role="status" data-dirty={hasChanges}>
        {hasChanges ? `未保存调整 ${changes.length} 个页面` : "暂无未保存调整"}
      </span>
      <Input className={styles.reason} prefix={<FileTextOutlined />} showCount aria-label="角色授权调整原因（必填）"
        disabled={controlsDisabled} value={reason} onChange={(event) => setReason(event.target.value)}
        placeholder="填写角色授权调整原因" maxLength={500} />
      <div className={styles.footerActions}>
        <Button loading={pendingAction === "preview"} onClick={() => void previewChanges("preview")} disabled={controlsDisabled}>预览</Button>
        <Button type="primary" aria-label="保存" aria-busy={savePending} loading={savePending}
          onClick={() => void previewChanges("save")} disabled={controlsDisabled}>保存</Button>
      </div>
    </footer>

    {result && historyOpen !== undefined && <PagePermissionHistoryDrawer targetType="role" targetId={role.id} targetName={role.name}
      grantVersion={result.grant_version} open={historyOpen} onClose={() => setHistoryOpen(false)} onRolledBack={() => {
        setLoading(true); setRefreshVersion((version) => version + 1)
      }} />}
  </div>
}
