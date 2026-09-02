"use client"

import { useCallback, useEffect, useState } from "react"
import { PAGE_DATA_SCOPE_VISIBLE } from "@/lib/page-permission-editor"
import { App, Button, Checkbox, Drawer, Input, Popconfirm, Table, Tag } from "antd"
import { AppstoreOutlined, PlusOutlined } from "@ant-design/icons"
import type { AdminUserItem, RoleItem } from "@/lib/api/client/admin"
import { fetchAdminUsers, fetchDataScopes } from "@/lib/api/client/admin"
import type { DepartmentItem } from "@/lib/api/server/admin"
import { DataScopeConfig, type DataScopeSelection } from "./DataScopeConfig"
import { assignUserRoles, deleteDataScope, removeUserRole, saveUserDataScope } from "@/actions/admin"
import UserModuleAccessDrawer, { type ModuleAccessUser } from "./UserModuleAccessDrawer"

interface UserRoleManagerProps {
  initialRoles: RoleItem[]
  initialDepartments: DepartmentItem[]
}

export function UserRoleManager({ initialRoles, initialDepartments }: UserRoleManagerProps) {
  const { message } = App.useApp()
  const [users, setUsers] = useState<AdminUserItem[]>([])
  const [loading, setLoading] = useState(false)
  const [keyword, setKeyword] = useState("")
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editingUser, setEditingUser] = useState<AdminUserItem | null>(null)
  const [selectedRoleIds, setSelectedRoleIds] = useState<string[]>([])
  const [dataScope, setDataScope] = useState<DataScopeSelection>({
    scopeType: null,
    departmentNames: [],
  })
  const [dataScopeRuleId, setDataScopeRuleId] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [moduleAccessUser, setModuleAccessUser] = useState<ModuleAccessUser | null>(null)

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
    setEditingUser(user)
    setSelectedRoleIds(user.roles.map((r) => r.id))
    setDataScope({ scopeType: null, departmentNames: [] })
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
      }
    } catch {
      // 数据范围加载失败不阻塞角色分配
    }
  }

  const handleSave = async () => {
    if (!editingUser) return
    setSaving(true)
    try {
      await assignUserRoles(editingUser.id, selectedRoleIds)
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
      message.success("角色已分配")
      setDrawerOpen(false)
      loadUsers(keyword)
    } catch (e) {
      message.error(e instanceof Error ? e.message : "分配失败")
    } finally {
      setSaving(false)
    }
  }

  const handleRemoveRole = async (user: AdminUserItem, roleId: string) => {
    try {
      await removeUserRole(user.id, roleId)
      message.success("角色已移除")
      loadUsers(keyword)
    } catch (e) {
      message.error(e instanceof Error ? e.message : "移除失败")
    }
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
            <Tag key={r.id} color={r.is_system ? "gold" : "blue"} closable onClose={() => handleRemoveRole(record, r.id)}>
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
        size={420}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        extra={
          <Button type="primary" loading={saving} onClick={handleSave}>
            保存
          </Button>
        }
      >
        <div className="text-sm font-medium mb-2">勾选角色（全量替换该用户的角色）</div>
        <Checkbox.Group
          value={selectedRoleIds}
          onChange={(vals) => setSelectedRoleIds(vals as string[])}
          options={initialRoles.map((r) => ({
            label: r.code === 'super_admin' ? '系统管理员（全部权限）' : r.name,
            value: r.id,
          }))}
          className="flex flex-col gap-2"
        />

        {PAGE_DATA_SCOPE_VISIBLE && <div className="mt-4">
          <div className="text-sm font-medium mb-2">可见部门（用户级覆盖，可选）</div>
          <div className="border rounded-md p-3">
            <DataScopeConfig
              departments={initialDepartments}
              value={dataScope}
              onChange={setDataScope}
            />
          </div>
        </div>}
        <Popconfirm title="注意" description="保存将全量替换该用户角色，确认？" onConfirm={handleSave}>
          <Button type="primary" className="mt-4">
            保存
          </Button>
        </Popconfirm>
      </Drawer>

      <UserModuleAccessDrawer
        user={moduleAccessUser}
        open={Boolean(moduleAccessUser)}
        onClose={() => setModuleAccessUser(null)}
      />

    </div>
  )
}
