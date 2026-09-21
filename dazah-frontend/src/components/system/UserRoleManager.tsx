"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { PAGE_DATA_SCOPE_VISIBLE } from "@/lib/page-permission-editor"
import { Alert, App, Button, Checkbox, Drawer, Input, Table, Tag, Typography } from "antd"
import { AppstoreOutlined, PlusOutlined } from "@ant-design/icons"
import type { AdminUserItem, RoleItem } from "@/lib/api/client/admin"
import { fetchAdminUsers, fetchDataScopes } from "@/lib/api/client/admin"
import type { DepartmentItem } from "@/lib/api/server/admin"
import { DataScopeConfig, type DataScopeSelection } from "./DataScopeConfig"
import { assignUserRoles, deleteDataScope, saveUserDataScope } from "@/actions/admin"
import UserModuleAccessDrawer, { type ModuleAccessUser } from "./UserModuleAccessDrawer"

interface UserRoleManagerProps {
  initialRoles: RoleItem[]
  initialDepartments: DepartmentItem[]
}

export function UserRoleManager({ initialRoles, initialDepartments }: UserRoleManagerProps) {
  const { message, modal } = App.useApp()
  const [users, setUsers] = useState<AdminUserItem[]>([])
  const [loading, setLoading] = useState(false)
  const [keyword, setKeyword] = useState("")
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editingUser, setEditingUser] = useState<AdminUserItem | null>(null)
  const [selectedRoleIds, setSelectedRoleIds] = useState<string[]>([])
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
  const addedRoles = useMemo(() => initialRoles.filter((role) =>
    selectedRoleSet.has(role.id) && !originalRoleSet.has(role.id)), [initialRoles, originalRoleSet, selectedRoleSet])
  const removedRoles = useMemo(() => initialRoles.filter((role) =>
    originalRoleSet.has(role.id) && !selectedRoleSet.has(role.id)), [initialRoles, originalRoleSet, selectedRoleSet])
  const roleChanged = addedRoles.length > 0 || removedRoles.length > 0
  const scopeChanged = JSON.stringify({ ...dataScope, departmentNames: [...dataScope.departmentNames].sort() }) !==
    JSON.stringify({ ...originalDataScope, departmentNames: [...originalDataScope.departmentNames].sort() })
  const hasChanges = roleChanged || scopeChanged
  const selectedSystemAdmin = initialRoles.some((role) => role.code === "super_admin" && selectedRoleSet.has(role.id))
  const filteredRoles = useMemo(() => {
    const normalized = roleSearch.trim().toLocaleLowerCase()
    if (!normalized) return initialRoles
    return initialRoles.filter((role) => [role.name, role.code, role.description || ""]
      .some((value) => value.toLocaleLowerCase().includes(normalized)))
  }, [initialRoles, roleSearch])

  const loadUsers = useCallback(async (kw = "") => {
    setLoading(true)
    try {
      const data = await fetchAdminUsers()
      const filtered = kw
        ? data.items.filter(
            (u) => u.name.includes(kw) || (u.department ?? "").includes(kw)
          )
        : data.items
      setUsers(filtered)
    } catch (e) {
      message.error(e instanceof Error ? e.message : "用户加载失败")
    } finally {
      setLoading(false)
    }
  }, [message])

  useEffect(() => {
    queueMicrotask(loadUsers)
  }, [loadUsers])

  const openAssign = async (user: AdminUserItem) => {
    const roleIds = user.roles.map((r) => r.id)
    setEditingUser(user)
    setSelectedRoleIds(roleIds)
    setOriginalRoleIds(roleIds)
    setRoleSearch("")
    setReason("")
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
    try {
      await assignUserRoles(editingUser.id, selectedRoleIds, {
        expectedGrantVersion: editingUser.grant_version,
        reason: reason.trim(),
      })
      // 保存用户级可见部门配置（个例覆盖，如高管看全厂）
      if (PAGE_DATA_SCOPE_VISIBLE && dataScope.scopeType === null) {
        if (dataScopeRuleId) await deleteDataScope(dataScopeRuleId)
      } else if (PAGE_DATA_SCOPE_VISIBLE && dataScope.scopeType !== null) {
        await saveUserDataScope(
          editingUser.id,
          dataScope.scopeType,
          dataScope.departmentNames,
        )
      }
      message.success(`角色分配已更新：新增 ${addedRoles.length} 个，移除 ${removedRoles.length} 个`)
      setDrawerOpen(false)
      loadUsers(keyword)
    } catch (e) {
      message.error(e instanceof Error ? e.message : "分配失败")
    } finally {
      setSaving(false)
    }
  }

  const toggleRole = (role: RoleItem, checked: boolean) => {
    const administratorIds = initialRoles.filter((item) =>
      item.code === "super_admin" || item.code === "ordinary_admin").map((item) => item.id)
    if (checked && administratorIds.includes(role.id)) {
      setSelectedRoleIds([role.id])
      setDataScope(originalDataScope)
      return
    }
    setSelectedRoleIds((current) => {
      const withoutSystemAdmin = current.filter((id) => !administratorIds.includes(id))
      return checked
        ? [...new Set([...withoutSystemAdmin, role.id])]
        : current.filter((id) => id !== role.id)
    })
  }

  const previewSave = () => {
    if (!hasChanges) { message.info("角色和兼容部门范围均未变化"); return }
    if (!reason.trim()) { message.warning("请填写本次授权调整原因"); return }
    if (dataScope.scopeType === "departments" && !dataScope.departmentNames.length) {
      message.warning("指定部门范围至少选择一个部门")
      return
    }
    modal.confirm({
      title: `确认调整 ${editingUser?.name || "用户"} 的角色？`,
      width: 640,
      okText: "确认保存",
      cancelText: "继续检查",
      content: <div className="space-y-3 pt-2">
        <Alert showIcon type={selectedSystemAdmin ? "warning" : "info"}
          title={selectedSystemAdmin ? "系统管理员将拥有全部权限" : "多个角色的页面权限将合并生效"}
          description="角色提供页面权限基线：基础权限与高风险操作取并集，数据范围按页面合并；已有用户页面覆盖仍优先于角色基线。" />
        <div><Typography.Text strong>新增角色：</Typography.Text>{addedRoles.length
          ? addedRoles.map((role) => <Tag key={role.id} color="green">{role.name}</Tag>)
          : <Typography.Text type="secondary">无</Typography.Text>}</div>
        <div><Typography.Text strong>移除角色：</Typography.Text>{removedRoles.length
          ? removedRoles.map((role) => <Tag key={role.id} color="red">{role.name}</Tag>)
          : <Typography.Text type="secondary">无</Typography.Text>}</div>
        <div><Typography.Text strong>调整原因：</Typography.Text>{reason.trim()}</div>
      </div>,
      onOk: handleSave,
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
            <Tag key={r.id} color={r.is_system ? "gold" : "blue"}>
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
            模块访问
          </Button>
        </div>
      ),
    },
  ]

  return (
    <div>
      <div className="mb-3 max-w-sm">
        <Input.Search
          placeholder="按姓名 / 部门搜索"
          allowClear
          onSearch={(v) => {
            setKeyword(v)
            loadUsers(v)
          }}
        />
      </div>
      <Table
        rowKey="id"
        columns={columns}
        dataSource={users}
        loading={loading}
        pagination={false}
        size="middle"
        scroll={{ x: 900 }}
      />

      <Drawer
        title={editingUser ? `分配角色：${editingUser.name}` : "分配角色"}
        size="min(620px, 100vw)"
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        footer={<div className="flex justify-end gap-2">
          <Button onClick={() => setDrawerOpen(false)}>取消</Button>
          <Button type="primary" loading={saving} disabled={!hasChanges} onClick={previewSave}>预览并保存</Button>
        </div>}
      >
        <Alert className="mb-4" showIcon type="info" title="角色决定页面权限基线"
          description="多个普通角色会合并生效：页面基础权限和附加高风险操作取并集，页面数据范围按规则合并；用户页面覆盖优先。系统管理员拥有全部权限，与其他角色无需同时选择。" />
        <div className="mb-4 rounded-lg border border-[var(--color-border)] p-3">
          <Typography.Text strong>{editingUser?.name}</Typography.Text>
          <Typography.Text type="secondary" className="ml-2">
            {[editingUser?.department, editingUser?.position].filter(Boolean).join(" · ") || "未维护部门与岗位"}
          </Typography.Text>
          <div className="mt-2 flex flex-wrap gap-2">
            <Tag color="blue">已选 {selectedRoleIds.length} 个角色</Tag>
            {!!addedRoles.length && <Tag color="green">新增 {addedRoles.length}</Tag>}
            {!!removedRoles.length && <Tag color="red">移除 {removedRoles.length}</Tag>}
          </div>
        </div>
        <div className="mb-2 flex items-center justify-between gap-3">
          <Typography.Text strong>手动角色</Typography.Text>
          <Input.Search allowClear value={roleSearch} onChange={(event) => setRoleSearch(event.target.value)}
            placeholder="搜索角色名称或编码" className="max-w-64" aria-label="搜索可分配角色" />
        </div>
        <div className="max-h-[360px] space-y-2 overflow-y-auto pr-1">
          {filteredRoles.map((role) => <label key={role.id}
            className={`block cursor-pointer rounded-lg border p-3 transition-colors ${selectedRoleSet.has(role.id) ? "border-[var(--color-primary)] bg-[var(--color-surface)]" : "border-[var(--color-border)]"}`}>
            <Checkbox checked={selectedRoleSet.has(role.id)} onChange={(event) => toggleRole(role, event.target.checked)}>
              <Typography.Text strong>{role.code === "super_admin" ? "系统管理员" : role.name}</Typography.Text>
            </Checkbox>
            <div className="ml-6 mt-1">
              <Typography.Text type="secondary" className="text-xs">{role.code}</Typography.Text>
              <Typography.Paragraph type="secondary" className="mb-0 mt-1 text-xs">
                {role.code === "super_admin" ? "拥有全部模块、页面、普通操作和高风险操作权限。" : role.code === "ordinary_admin" ? "拥有业务管理员权限，但不能进入系统设置。" : role.description || "页面权限基线请在角色管理中查看和维护。"}
              </Typography.Paragraph>
            </div>
          </label>)}
          {!filteredRoles.length && <Typography.Text type="secondary">没有匹配的角色</Typography.Text>}
        </div>
        {selectedSystemAdmin && <Alert className="mt-3" showIcon type="warning"
          title="当前选择将授予系统管理员权限" description="系统管理员拥有全部权限，选择后已自动取消其他普通角色。" />}

        {PAGE_DATA_SCOPE_VISIBLE && selectedSystemAdmin && <Alert className="mt-4" showIcon type="info"
          title="系统管理员不受部门范围限制"
          description="当前兼容部门范围配置会保留但不参与鉴权；移除系统管理员角色后会重新生效。" />}
        {PAGE_DATA_SCOPE_VISIBLE && !selectedSystemAdmin && <div className="mt-4">
          <Typography.Text strong>兼容部门范围</Typography.Text>
          <Typography.Paragraph type="secondary" className="mb-2 text-xs">
            仅用于尚未接入页面级数据范围的功能；已接入页面权限的页面，请通过列表中的“页面权限”配置数据范围。
          </Typography.Paragraph>
          <div className="border rounded-md p-3">
            <DataScopeConfig
              departments={initialDepartments}
              value={dataScope}
              onChange={setDataScope}
            />
          </div>
        </div>}
        <Input.TextArea className="mt-4" value={reason} onChange={(event) => setReason(event.target.value)}
          maxLength={500} showCount placeholder="填写本次角色授权调整原因" aria-label="角色授权调整原因" />
      </Drawer>

      <UserModuleAccessDrawer
        user={moduleAccessUser}
        open={Boolean(moduleAccessUser)}
        onClose={() => setModuleAccessUser(null)}
      />

    </div>
  )
}
