"use client"

import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react"
import { PAGE_DATA_SCOPE_VISIBLE } from "@/lib/page-permission-editor"
import { App, Button, Checkbox, ConfigProvider, Drawer, Input, Popover, Table, Tag, Typography } from "antd"
import Alert from "@/components/shared/PlatformNotice"
import { AppstoreOutlined, DownOutlined, PlusOutlined, SearchOutlined, UpOutlined } from "@ant-design/icons"
import type { AdminUserItem, RoleItem } from "@/lib/api/client/admin"
import { fetchAdminUsers, fetchDataScopes } from "@/lib/api/client/admin"
import type { DepartmentItem } from "@/lib/api/server/admin"
import { DataScopeConfig, type DataScopeSelection } from "./DataScopeConfig"
import { assignUserRoles, deleteDataScope, saveUserDataScope } from "@/actions/admin"
import UserModuleAccessDrawer, { type ModuleAccessUser } from "./UserModuleAccessDrawer"
import styles from "./UserRoleManager.module.css"
import { roleTagColor } from "@/lib/role-tag"

interface UserRoleManagerProps {
  initialRoles: RoleItem[]
  initialDepartments: DepartmentItem[]
}

interface UserListQuery {
  keyword: string
  page: number
}

type UserListResult = { query: UserListQuery } & (
  { items: AdminUserItem[]; total: number; error?: never } | { error: string }
)

const USER_PAGE_SIZE = 20
const ROLE_ASSIGNMENT_REASON_PRESETS = ["岗位职责调整", "临时工作授权", "权限回收"]

function roleOrder(code: string) {
  if (code === "super_admin") return 0
  if (code === "ordinary_admin") return 1
  return 2
}

export function UserRoleManager({ initialRoles, initialDepartments }: UserRoleManagerProps) {
  const { message, modal } = App.useApp()
  const [query, setQuery] = useState<UserListQuery>({ keyword: "", page: 1 })
  const [listResult, setListResult] = useState<UserListResult | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [openFooterPanel, setOpenFooterPanel] = useState<"scope" | "reason" | null>(null)
  const scopePanelId = useId()
  const reasonPanelId = useId()
  const scopeTrigger = useRef<HTMLButtonElement>(null)
  const reasonTrigger = useRef<HTMLButtonElement>(null)
  const scopeOpen = drawerOpen && openFooterPanel === "scope"
  const reasonOpen = drawerOpen && openFooterPanel === "reason"
  const closeFooterPanel = (panel: "scope" | "reason") => {
    setOpenFooterPanel(null)
    const trigger = panel === "scope" ? scopeTrigger : reasonTrigger
    trigger.current?.focus()
  }
  const [editingUser, setEditingUser] = useState<AdminUserItem | null>(null)
  const [selectedRoleIds, setSelectedRoleIds] = useState<string[]>([])
  const [selectedRolesExpanded, setSelectedRolesExpanded] = useState(false)
  const [selectedRolesOverflow, setSelectedRolesOverflow] = useState(false)
  const selectedRolesId = useId()
  const observeSelectedRoles = useCallback((viewport: HTMLDivElement | null) => {
    const content = viewport?.firstElementChild
    if (!viewport || !content) return
    const observer = new ResizeObserver(() => {
      setSelectedRolesOverflow(viewport.scrollHeight > viewport.clientHeight)
    })
    observer.observe(viewport)
    observer.observe(content)
    return () => observer.disconnect()
  }, [])
  const [originalRoleIds, setOriginalRoleIds] = useState<string[]>([])
  const [roleSearch, setRoleSearch] = useState("")
  const [reason, setReason] = useState("")
  const [dataScope, setDataScope] = useState<DataScopeSelection>({
    scopeType: null,
    departmentNames: [],
  })
  const [dataScopeRuleId, setDataScopeRuleId] = useState<string | null>(null)
  const [originalDataScope, setOriginalDataScope] = useState<DataScopeSelection>({
    scopeType: null,
    departmentNames: [],
  })
  const [saving, setSaving] = useState(false)
  const [moduleAccessUser, setModuleAccessUser] = useState<ModuleAccessUser | null>(null)

  const selectedRoleSet = useMemo(() => new Set(selectedRoleIds), [selectedRoleIds])
  const originalRoleSet = useMemo(() => new Set(originalRoleIds), [originalRoleIds])
  const openingRoles = editingUser?.roles ?? []
  const canRestoreRoles = openingRoles.length !== selectedRoleSet.size ||
    openingRoles.some((role) => !selectedRoleSet.has(role.id))
  const knownRoles = [...new Map([...openingRoles, ...initialRoles].map((role) => [role.id, role])).values()]
  const addedRoles = knownRoles.filter((role) => selectedRoleSet.has(role.id) && !originalRoleSet.has(role.id))
  const removedRoles = knownRoles.filter((role) => originalRoleSet.has(role.id) && !selectedRoleSet.has(role.id))
  const roleChanged = selectedRoleSet.size !== originalRoleSet.size ||
    selectedRoleIds.some((id) => !originalRoleSet.has(id))
  const scopeChanged = JSON.stringify({ ...dataScope, departmentNames: [...dataScope.departmentNames].sort() }) !==
    JSON.stringify({ ...originalDataScope, departmentNames: [...originalDataScope.departmentNames].sort() })
  const hasChanges = roleChanged || scopeChanged
  const selectedSystemAdmin = initialRoles.some((role) => role.code === "super_admin" && selectedRoleSet.has(role.id))
  const scopeSummary = dataScope.scopeType === "all" ? "全部部门" : dataScope.scopeType === "departments"
    ? `指定部门（${dataScope.departmentNames.length}）` : "本部门 + 子部门"
  const filteredRoles = useMemo(() => {
    const normalized = roleSearch.trim().toLocaleLowerCase()
    return initialRoles.filter((role) => [role.name, role.code, role.description || ""]
      .some((value) => value.toLocaleLowerCase().includes(normalized)))
      .sort((first, second) => roleOrder(first.code) - roleOrder(second.code))
  }, [initialRoles, roleSearch])

  useEffect(() => {
    let cancelled = false
    fetchAdminUsers({ keyword: query.keyword, offset: (query.page - 1) * USER_PAGE_SIZE, limit: USER_PAGE_SIZE })
      .then((data) => {
        if (cancelled) return
        const lastPage = Math.max(1, Math.ceil(data.total / USER_PAGE_SIZE))
        if (query.page > lastPage) {
          setQuery((current) => current === query ? { ...current, page: lastPage } : current)
          return
        }
        setListResult({ query, ...data })
      })
      .catch((cause: unknown) => {
        if (cancelled) return
        const error = cause instanceof Error ? cause.message : "用户加载失败"
        message.error(error)
        setListResult({ query, error })
      })
    return () => { cancelled = true }
  }, [message, query])

  const loading = listResult?.query !== query
  const loadError = loading ? undefined : listResult.error
  const refreshUsers = () => setQuery((current) => ({ ...current }))

  const openAssign = async (user: AdminUserItem) => {
    const roleIds = user.roles.map((r) => r.id)
    setEditingUser(user)
    setSelectedRolesExpanded(false)
    setSelectedRoleIds(roleIds)
    setOriginalRoleIds(roleIds)
    setRoleSearch("")
    setReason("")
    setOpenFooterPanel(null)
    const defaultScope = { scopeType: null, departmentNames: [] } satisfies DataScopeSelection
    setDataScope(defaultScope)
    setOriginalDataScope(defaultScope)
    setDataScopeRuleId(null)
    setDrawerOpen(true)
    if (!PAGE_DATA_SCOPE_VISIBLE) return
    try {
      const scopeRules = await fetchDataScopes()
      const rule = scopeRules.find((r) => r.user_id === user.id)
      if (rule) {
        setDataScopeRuleId(rule.id)
        setDataScope({
          scopeType: rule.scope_type,
          departmentNames: rule.department_names ?? [],
        })
        setOriginalDataScope({
          scopeType: rule.scope_type,
          departmentNames: rule.department_names ?? [],
        })
      }
    } catch {
      // 数据范围加载失败不阻塞角色分配
    }
  }

  const handleSave = async () => {
    if (!editingUser) return
    setSaving(true)
    setOpenFooterPanel(null)
    let rolesSaved = false
    try {
      if (roleChanged) {
        const result = await assignUserRoles(editingUser.id, selectedRoleIds, {
          expectedGrantVersion: editingUser.grant_version,
          reason: reason.trim(),
        })
        if (!result.ok) { message.error(result.message); return }
        rolesSaved = true
        setEditingUser({ ...editingUser, grant_version: result.data.grant_version })
        setOriginalRoleIds([...selectedRoleIds])
        refreshUsers()
      }
      // 保存用户级可见部门配置（个例覆盖，如高管看全厂）
      if (PAGE_DATA_SCOPE_VISIBLE && scopeChanged) {
        const result = dataScope.scopeType === null
          ? dataScopeRuleId ? await deleteDataScope(dataScopeRuleId) : null
          : await saveUserDataScope(editingUser.id, dataScope.scopeType, dataScope.departmentNames)
        if (result && !result.ok) {
          message.error(`${rolesSaved ? "角色已保存，" : ""}部门数据范围保存失败：${result.message}`)
          return
        }
        setOriginalDataScope({ ...dataScope, departmentNames: [...dataScope.departmentNames] })
      }
      message.success(roleChanged
        ? `角色分配已更新：新增 ${addedRoles.length} 个，移除 ${removedRoles.length} 个`
        : "部门数据范围已更新")
      setDrawerOpen(false)
      if (!rolesSaved) refreshUsers()
    } catch (e) {
      message.error(rolesSaved ? "角色已保存，请刷新确认部门数据范围是否已保存"
        : e instanceof Error ? e.message : "分配失败")
    } finally {
      setSaving(false)
    }
  }

  const toggleRole = (role: RoleItem, checked: boolean) => {
    if (!checked) {
      setSelectedRoleIds((current) => current.filter((id) => id !== role.id))
      return
    }
    const roleOptions = [...initialRoles, ...(editingUser?.roles ?? [])]
    const administratorIds = new Set(roleOptions.filter((item) =>
      item.code === "super_admin" || item.code === "ordinary_admin").map((item) => item.id))
    const selectingAdministrator = administratorIds.has(role.id)
    const conflicts = selectedRoleIds.filter((id) => id !== role.id && (selectingAdministrator || administratorIds.has(id)))
    const applySelection = () => {
      const removedIds = new Set(conflicts)
      setSelectedRoleIds((current) => [...new Set([...current.filter((id) => !removedIds.has(id)), role.id])])
      if (selectingAdministrator) {
        setOpenFooterPanel((panel) => panel === "scope" ? null : panel)
        setDataScope(originalDataScope)
      }
    }
    if (!conflicts.length) {
      applySelection()
      return
    }
    const removedNames = conflicts.map((id) => roleOptions.find((item) => item.id === id)?.name ?? id)
    setOpenFooterPanel(null)
    modal.confirm({
      title: `切换为「${role.name}」？`,
      centered: true,
      content: <div>
        <p>管理员角色必须单独分配。确认后将从本次待保存的配置中移除以下 {conflicts.length} 个角色：</p>
        <p>{removedNames.join("、")}</p>
        {selectingAdministrator && scopeChanged && <p>本次尚未保存的部门数据范围调整也将被取消。</p>}
      </div>,
      okText: "确认切换",
      cancelText: "保留当前选择",
      onOk: applySelection,
    })
  }

  const permissionSummary = <div className="space-y-3 pt-2">
    <Alert showIcon type={selectedSystemAdmin ? "warning" : "info"}
      title={selectedSystemAdmin ? "系统管理员将拥有全部权限" : "多个角色的页面权限合并生效，模块入口随有效页面访问权限自动开通或关闭。"}
      description="角色提供页面权限基线：基础权限与高风险操作取并集，数据范围按页面合并；已有用户页面覆盖仍优先于角色基线。模块内至少一个页面具有有效访问权限时，模块入口自动开通；撤销最后一个可访问页面后，入口自动关闭。系统管理员默认拥有全部模块访问权限。" />
    <div><Typography.Text strong>已选角色：</Typography.Text>{selectedRoleIds.length
      ? initialRoles.filter((role) => selectedRoleSet.has(role.id)).map((role) => <Tag key={role.id} color={roleTagColor(role.code, role.is_system)}>{role.name}</Tag>)
      : <Typography.Text type="secondary">未分配角色</Typography.Text>}</div>
    <div><Typography.Text strong>新增角色：</Typography.Text>{addedRoles.length
      ? addedRoles.map((role) => <Tag key={role.id} color="green">{role.name}</Tag>)
      : <Typography.Text type="secondary">无</Typography.Text>}</div>
    <div><Typography.Text strong>移除角色：</Typography.Text>{removedRoles.length
      ? removedRoles.map((role) => <Tag key={role.id} color="red">{role.name}</Tag>)
      : <Typography.Text type="secondary">无</Typography.Text>}</div>
    {PAGE_DATA_SCOPE_VISIBLE && <div><Typography.Text strong>兼容部门范围：</Typography.Text>
      {selectedSystemAdmin ? "系统管理员不受部门范围限制" : dataScope.scopeType === "all" ? "全部部门"
        : dataScope.scopeType === "departments" ? dataScope.departmentNames.join("、") || "尚未选择部门" : "本部门 + 子部门"}
    </div>}
    <Typography.Paragraph type="secondary" className="mb-0">
      此处预览角色与范围配置；具体页面的有效权限还取决于用户页面覆盖和页面权限规则，模块入口由最终有效页面权限计算。
    </Typography.Paragraph>
  </div>

  const previewPermissions = () => modal.info({
    title: `${editingUser?.name || "用户"} · 权限配置预览`,
    width: 640,
    centered: true,
    icon: null,
    okText: "返回编辑",
    content: permissionSummary,
  })

  const showPermissionRules = () => modal.info({
    title: "角色与数据范围规则",
    width: 640,
    centered: true,
    icon: null,
    okText: "我知道了",
    content: <div>
      <Typography.Text strong>模块入口随有效页面权限自动生效</Typography.Text>
      <p>为角色配置页面权限后，只需给账号分配角色。模块内至少一个页面具有有效访问权限时，模块入口自动开通；撤销最后一个可访问页面后，入口自动关闭。多个角色合并计算，用户页面覆盖优先；明确拒绝的页面不参与入口开通。系统管理员默认拥有全部模块访问权限。</p>
      <Typography.Text strong>角色决定页面权限基线</Typography.Text>
      <p>多个普通角色会合并生效：页面基础权限和附加高风险操作取并集，页面数据范围按规则合并；用户页面覆盖优先。系统管理员拥有全部权限，普通管理员不能进入系统设置，两类管理员角色均单独选择。兼容部门范围仅用于尚未接入页面级数据范围的功能。</p>
    </div>,
  })

  const previewSave = () => {
    if (!hasChanges) { message.info("角色和兼容部门范围均未变化"); return }
    if (!reason.trim()) {
      setOpenFooterPanel("reason")
      message.warning("请填写本次授权调整原因")
      return
    }
    if (dataScope.scopeType === "departments" && !dataScope.departmentNames.length) {
      setOpenFooterPanel("scope")
      message.warning("指定部门范围至少选择一个部门")
      return
    }
    setOpenFooterPanel(null)
    modal.confirm({
      title: `确认调整 ${editingUser?.name || "用户"} 的角色？`,
      width: 640,
      centered: true,
      icon: null,
      okText: "确认保存",
      cancelText: "继续检查",
      content: <div className="space-y-3 pt-2">
        {permissionSummary}
        <div><Typography.Text strong>调整原因：</Typography.Text>{reason.trim()}</div>
      </div>,
      onOk: handleSave,
    })
  }

  const closeAssign = () => {
    if (saving) return
    if (!hasChanges && !reason.trim()) { setDrawerOpen(false); return }
    modal.confirm({
      title: "放弃未保存的角色分配调整？",
      centered: true,
      icon: null,
      content: <Alert showIcon type="warning" title="关闭后，本次角色、部门范围调整和授权原因将丢失。" />,
      okText: "放弃更改",
      cancelText: "继续编辑",
      onOk: () => setDrawerOpen(false),
    })
  }

  const columns = [
    { title: "姓名", dataIndex: "name", key: "name" },
    { title: "部门", dataIndex: "department", key: "department" },
    { title: "岗位", dataIndex: "position", key: "position" },
    {
      title: "角色",
      key: "roles",
      render: (_: unknown, record: AdminUserItem) => (
        <div className="flex flex-wrap gap-1">
          {record.roles.map((r) => (
            <Tag key={r.id} color={roleTagColor(r.code, r.is_system)}>
              {r.name}
            </Tag>
          ))}
          {record.roles.length === 0 && <Tag>未分配</Tag>}
        </div>
      ),
    },
    {
      title: "操作",
      key: "actions",
      width: 240,
      fixed: "right" as const,
      render: (_: unknown, record: AdminUserItem) => (
        <div className="flex flex-wrap gap-2">
          <Button size="small" icon={<PlusOutlined />} onClick={() => openAssign(record)}>
            分配角色
          </Button>
          <Button
            size="small"
            icon={<AppstoreOutlined />}
            onClick={() => setModuleAccessUser({
              id: record.id,
              name: record.name,
              isSystemAdmin: record.roles.some((role) => role.code === "super_admin"),
            })}
          >
            有效权限
          </Button>
        </div>
      ),
    },
  ]

  return (
    <div>
      <Alert className="mb-3" type="info" showIcon
        title="为角色配置页面权限后，只需分配角色；模块入口随有效页面访问权限自动生效。"
        onLearnRules={showPermissionRules} />
      <div className="mb-3 max-w-sm">
        <Input.Search
          placeholder="按姓名、部门、账号、邮箱、手机号或工号搜索"
          allowClear
          onSearch={(value) => setQuery({ keyword: value.trim(), page: 1 })}
        />
      </div>
      <Table
        rowKey="id"
        columns={columns}
        dataSource={!loading && listResult.error === undefined ? listResult.items : []}
        loading={loading}
        locale={{ emptyText: loadError !== undefined ? (
          <div>
            <span>{loadError}</span>
            <Button type="link" onClick={refreshUsers}>重试</Button>
          </div>
        ) : query.keyword ? "没有符合条件的用户" : "暂无用户" }}
        pagination={{
          current: query.page,
          total: listResult?.query.keyword === query.keyword && listResult.error === undefined ? listResult.total : 0,
          pageSize: USER_PAGE_SIZE,
          showSizeChanger: false,
          onChange: (page) => setQuery((current) => ({ ...current, page })),
        }}
        size="middle"
        scroll={{ x: 900 }}
      />

      <Drawer
        rootClassName={styles.drawer}
        title={<Typography.Title level={4} className={styles.title}>分配角色{editingUser ? ` · ${editingUser.name}` : ""}</Typography.Title>}
        size="min(var(--assignment-drawer-width), 100vw)"
        placement="right"
        open={drawerOpen}
        onClose={closeAssign}
        closable={!saving}
        mask={{ closable: !saving }}
        footer={<div className={styles.footer} onKeyDown={(event) => {
          if (event.key !== "Escape" || !openFooterPanel) return
          event.stopPropagation()
          closeFooterPanel(openFooterPanel)
        }}>
          <div className={styles.footerFields}>
          {PAGE_DATA_SCOPE_VISIBLE && !selectedSystemAdmin && <div className={styles.footerControl}>
            <Popover placement="topLeft" trigger="click" open={scopeOpen}
              onOpenChange={(open) => setOpenFooterPanel((panel) => open ? "scope" : panel === "scope" ? null : panel)}
              getPopupContainer={(trigger) => trigger.parentElement ?? trigger} destroyOnHidden
              content={<section id={scopePanelId} aria-label="部门数据范围" className={styles.departmentScope}>
                <Typography.Paragraph type="secondary">
                  仅适用于尚未接入页面级数据范围的功能。其余范围在「页面权限」中配置。
                </Typography.Paragraph>
                <DataScopeConfig segmented departments={initialDepartments} value={dataScope} onChange={(selection) => {
                  setDataScope(selection)
                  if (selection.scopeType !== "departments") closeFooterPanel("scope")
                }} />
                {dataScope.scopeType === "departments" && <div className={styles.scopeActions}>
                  <Button size="small" type="primary" disabled={!dataScope.departmentNames.length} onClick={() => closeFooterPanel("scope")}>完成</Button>
                </div>}
              </section>}>
              <Button ref={scopeTrigger} disabled={saving} aria-expanded={scopeOpen}
                aria-controls={scopeOpen ? scopePanelId : undefined} iconPlacement="end"
                icon={scopeOpen ? <DownOutlined /> : <UpOutlined />}>
                <span className={styles.controlLabel}>部门数据范围</span>
                <span className={styles.controlValue}>{scopeSummary}</span>
              </Button>
            </Popover>
          </div>}
          <div className={`${styles.footerControl} ${styles.reasonControl}`}>
            <Popover placement="topLeft" trigger="click" open={reasonOpen}
              onOpenChange={(open) => setOpenFooterPanel((panel) => open ? "reason" : panel === "reason" ? null : panel)}
              getPopupContainer={(trigger) => trigger.parentElement ?? trigger} destroyOnHidden
              content={<section id={reasonPanelId} className={styles.reasonSection} aria-label="授权调整原因">
                <label htmlFor="role-assignment-reason" className={styles.reasonLabel}>授权调整原因</label>
                <div className={styles.reasonPresets} role="group" aria-label="预设授权调整原因">
                  {ROLE_ASSIGNMENT_REASON_PRESETS.map((preset) => (
                    <Button key={preset} size="small" onClick={() => {
                      setReason(preset)
                      closeFooterPanel("reason")
                    }}>{preset}</Button>
                  ))}
                </div>
                <Input id="role-assignment-reason" value={reason} onChange={(event) => setReason(event.target.value)}
                  maxLength={20} showCount
                  placeholder="填写本次角色授权调整原因" aria-label="角色授权调整原因" />
                <div className={styles.scopeActions}>
                  <Button size="small" onClick={() => closeFooterPanel("reason")}>完成</Button>
                </div>
              </section>}>
              <Button ref={reasonTrigger} disabled={saving} aria-expanded={reasonOpen}
                aria-controls={reasonOpen ? reasonPanelId : undefined} iconPlacement="end"
                icon={reasonOpen ? <DownOutlined /> : <UpOutlined />}>
                <span className={styles.controlLabel}>授权调整原因</span>
                <span className={styles.controlValue}>{reason.trim() || "待填写"}</span>
              </Button>
            </Popover>
          </div>
          </div>
          <div className={styles.footerActions}>
            <Button disabled={saving} onClick={closeAssign}>取消</Button>
            <Button className={styles.previewButton} disabled={saving} onClick={previewPermissions}>预览权限</Button>
            <Button type="primary" loading={saving} disabled={!hasChanges} onClick={previewSave}>保存</Button>
          </div>
        </div>}
      >
        <ConfigProvider componentDisabled={saving}>
        <div className={styles.body} data-system-admin={selectedSystemAdmin}>
        <div className={styles.rolesColumn}>
        <section aria-label="已选择的角色">
          <div className={styles.sectionHeading}>
            <div className={styles.selectionSummary}>
              <Typography.Title level={5}>已选择 {selectedRoleIds.length} 个角色</Typography.Title>
              {!!addedRoles.length && <Tag color="green">新增 {addedRoles.length}</Tag>}
              {!!removedRoles.length && <Tag color="red">移除 {removedRoles.length}</Tag>}
            </div>
            <div className={styles.selectionActions}>
              {!!selectedRoleIds.length && (selectedRolesOverflow || selectedRolesExpanded) && <Button
                type="link" size="small" aria-expanded={selectedRolesExpanded} aria-controls={selectedRolesId}
                onClick={() => {
                  if (selectedRolesExpanded) document.getElementById(selectedRolesId)?.scrollTo({ top: 0 })
                  setSelectedRolesExpanded(!selectedRolesExpanded)
                }}>
                {selectedRolesExpanded ? "收起" : "展开全部"}
              </Button>}
              <Button type="link" size="small" disabled={saving || !canRestoreRoles}
                onClick={() => setSelectedRoleIds(openingRoles.map((role) => role.id))}>
                恢复原有选择
              </Button>
              <Button type="link" size="small" disabled={saving || !selectedRoleIds.length}
                onClick={() => {
                  setSelectedRolesExpanded(false)
                  setSelectedRoleIds([])
                }}>
                取消全部选择
              </Button>
            </div>
          </div>
          <div id={selectedRolesId} ref={observeSelectedRoles} className={styles.selectedRolesViewport}
            data-expanded={selectedRolesExpanded && selectedRoleIds.length > 0}>
          <div className={styles.selectedRoles}>
            {selectedRoleIds.map((id) => {
              const role = initialRoles.find((item) => item.id === id) || editingUser?.roles.find((item) => item.id === id)
              return <Tag key={id} className={styles.selectedRole} color={role ? roleTagColor(role.code, role.is_system) : undefined} closable={!saving}
                closeIcon={<button type="button" className={styles.removeRole} aria-label={`移除角色 ${role?.name || id}`} disabled={saving}>×</button>}
                onClose={() => setSelectedRoleIds((current) => current.filter((roleId) => roleId !== id))}>
                {role?.name || id}{role?.code ? ` · ${role.code}` : ""}
              </Tag>
            })}
            {!selectedRoleIds.length && <Typography.Text type="secondary">尚未选择角色，请从下方添加。</Typography.Text>}
          </div>
          </div>
        </section>
        <section aria-label="添加角色" className={styles.availableRoles}>
          <div className={styles.roleToolbar}>
            <Typography.Title level={5}>添加角色</Typography.Title>
            <Input allowClear prefix={<SearchOutlined />} value={roleSearch} onChange={(event) => setRoleSearch(event.target.value)}
              placeholder="搜索角色或编码" className={styles.roleSearch} aria-label="搜索可分配角色" />
          </div>
          <div className={styles.roleList}>
          {filteredRoles.map((role) => <div key={role.id} className={styles.roleRow} data-selected={selectedRoleSet.has(role.id)}>
            <Checkbox className={styles.roleChoice} checked={selectedRoleSet.has(role.id)} onChange={(event) => toggleRole(role, event.target.checked)}>
              <span className={styles.roleHeading}>
                <Typography.Text strong>{role.code === "super_admin" ? "系统管理员" : role.name}</Typography.Text>
                {role.code === "super_admin" && <Tag color="error">高风险</Tag>}
                {(role.code === "super_admin" || role.code === "ordinary_admin") && <Tag>单独分配</Tag>}
                <Typography.Text type="secondary" className={styles.roleCode}>{role.code}</Typography.Text>
              </span>
              <Typography.Text type="secondary" className={styles.roleDescription}>
                {role.code === "super_admin" ? "拥有全部模块、页面、普通操作和高风险操作权限。" : role.code === "ordinary_admin" ? "拥有业务管理员权限，但不能进入系统设置。" : role.description || "页面权限基线请在角色管理中查看和维护。"}
              </Typography.Text>
            </Checkbox>
          </div>)}
          {!filteredRoles.length && <div className={styles.emptyRoles}><Typography.Text type="secondary">没有匹配的角色，请调整搜索条件。</Typography.Text></div>}
          </div>
        </section>
        </div>
        {selectedSystemAdmin && <div className={styles.settingsColumn}>
        <Alert showIcon type="warning"
          title="保存后将授予全部系统权限" />

        {PAGE_DATA_SCOPE_VISIBLE && <Alert showIcon type="info"
          title="系统管理员不受部门范围限制"
          description="当前兼容部门范围配置会保留但不参与鉴权；移除系统管理员角色后会重新生效。" />}
        </div>}
        </div>
        </ConfigProvider>
      </Drawer>

      <UserModuleAccessDrawer
        user={moduleAccessUser}
        open={Boolean(moduleAccessUser)}
        onClose={() => setModuleAccessUser(null)}
      />

    </div>
  )
}
