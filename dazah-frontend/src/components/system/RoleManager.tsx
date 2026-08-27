"use client"

import { useMemo, useState } from "react"
import { App, Button, Checkbox, Drawer, Form, Input, Popconfirm, Spin, Table, Tag, Tree } from "antd"
import { PlusOutlined } from "@ant-design/icons"
import type { TreeDataNode } from "antd"
import type { PermissionItem, RoleItem } from "@/lib/api/client/admin"
import { fetchDataScopes, fetchRoleMenus } from "@/lib/api/client/admin"
import type { DepartmentItem } from "@/lib/api/server/admin"
import type { MenuFlatItem } from "@/lib/menu-tree"
import { buildMenuTree } from "@/lib/menu-tree"
import { DataScopeConfig, type DataScopeSelection } from "./DataScopeConfig"
import {
  createRole,
  deleteDataScope,
  deleteRole,
  saveRoleDataScope,
  setRoleMenus,
  setRolePermissions,
  updateRole,
} from "@/actions/admin"

interface RoleManagerProps {
  initialRoles: RoleItem[]
  initialPermissions: PermissionItem[]
  initialMenus: MenuFlatItem[]
  initialDepartments: DepartmentItem[]
}

export function RoleManager({
  initialRoles,
  initialPermissions,
  initialMenus,
  initialDepartments,
}: RoleManagerProps) {
  const { message } = App.useApp()
  const [roles, setRoles] = useState<RoleItem[]>(initialRoles)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editing, setEditing] = useState<RoleItem | "new" | null>(null)
  const [selectedPerms, setSelectedPerms] = useState<string[]>([])
  const [selectedMenuIds, setSelectedMenuIds] = useState<string[]>([])
  const [menuLoading, setMenuLoading] = useState(false)
  const [dataScope, setDataScope] = useState<DataScopeSelection>({
    scopeType: null,
    departmentNames: [],
  })
  const [dataScopeRuleId, setDataScopeRuleId] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm()

  // 权限目录按模块分组
  const permissionsByModule = useMemo(() => {
    const map = new Map<string, PermissionItem[]>()
    for (const p of initialPermissions) {
      const list = map.get(p.module) ?? []
      list.push(p)
      map.set(p.module, list)
    }
    return Array.from(map.entries()).sort((a, b) => a[0].localeCompare(b[0]))
  }, [initialPermissions])

  const openCreate = () => {
    setEditing("new")
    setSelectedPerms([])
    setSelectedMenuIds([])
    setDataScope({ scopeType: null, departmentNames: [] })
    setDataScopeRuleId(null)
    form.resetFields()
    setDrawerOpen(true)
  }

  const openEdit = async (role: RoleItem) => {
    setEditing(role)
    setSelectedPerms(role.permissions ?? [])
    setSelectedMenuIds([])
    setMenuLoading(true)
    setDataScope({ scopeType: null, departmentNames: [] })
    setDataScopeRuleId(null)
    form.setFieldsValue({
      name: role.name,
      code: role.code,
      description: role.description,
    })
    setDrawerOpen(true)
    try {
      const [menuIds, scopeRules] = await Promise.all([
        fetchRoleMenus(role.id),
        fetchDataScopes(),
      ])
      setSelectedMenuIds(menuIds)
      const rule = scopeRules.find((r) => r.role_id === role.id)
      if (rule) {
        setDataScopeRuleId(rule.id)
        setDataScope({
          scopeType: rule.scope_type,
          departmentNames: rule.department_names ?? [],
        })
      }
    } catch (e) {
      message.error(e instanceof Error ? e.message : "菜单加载失败")
    } finally {
      setMenuLoading(false)
    }
  }

  const handleSave = async () => {
    const values = await form.validateFields()
    setSaving(true)
    try {
      if (editing === "new") {
        const created = (await createRole({
          name: values.name,
          code: values.code,
          description: values.description,
        })) as RoleItem
        const permIds = initialPermissions
          .filter((p) => selectedPerms.includes(p.code))
          .map((p) => p.id)
        if (permIds.length > 0) {
          await setRolePermissions(created.id, permIds)
        }
        await setRoleMenus(created.id, selectedMenuIds)
        await saveRoleDataScopeForTarget(created.id, dataScope, dataScopeRuleId)
        message.success("角色已创建")
      } else if (editing) {
        await updateRole(editing.id, {
          name: values.name,
          description: values.description,
        })
        const permIds = initialPermissions
          .filter((p) => selectedPerms.includes(p.code))
          .map((p) => p.id)
        await setRolePermissions(editing.id, permIds)
        await setRoleMenus(editing.id, selectedMenuIds)
        await saveRoleDataScopeForTarget(editing.id, dataScope, dataScopeRuleId)
        message.success("角色已更新")
      }
      setDrawerOpen(false)
      window.location.reload()
    } catch (e) {
      message.error(e instanceof Error ? e.message : "保存失败")
    } finally {
      setSaving(false)
    }
  }

  // 保存可见部门配置：scopeType=null 且有存量规则 → 删除恢复默认；否则保存/覆盖
  const saveRoleDataScopeForTarget = async (
    targetRoleId: string,
    selection: DataScopeSelection,
    ruleId: string | null,
  ) => {
    if (selection.scopeType === null) {
      if (ruleId) await deleteDataScope(ruleId)
      return
    }
    await saveRoleDataScope(targetRoleId, selection.scopeType, selection.departmentNames)
  }

  const handleDelete = async (role: RoleItem) => {
    try {
      await deleteRole(role.id)
      message.success("角色已删除")
      setRoles((prev) => prev.filter((r) => r.id !== role.id))
    } catch (e) {
      message.error(e instanceof Error ? e.message : "删除失败")
    }
  }

  // 菜单权限树（目录/菜单/按钮 三级，按钮级权限码即按钮级权限）
  const menuTreeData = useMemo(() => {
    const toTreeData = (children: ReturnType<typeof buildMenuTree>): TreeDataNode[] =>
      children.map((node) => ({
        key: node.id,
        title: `${node.name}${node.permissionCode ? `（${node.permissionCode}）` : ""}`,
        children: node.children.length > 0 ? toTreeData(node.children) : undefined,
        disabled: node.status === "disabled",
      }))
    return toTreeData(buildMenuTree(initialMenus))
  }, [initialMenus])

  const columns = [
    { title: "角色名称", dataIndex: "name", key: "name" },
    { title: "编码", dataIndex: "code", key: "code" },
    {
      title: "类型",
      dataIndex: "is_system",
      key: "is_system",
      render: (v: boolean) =>
        v ? <Tag color="gold">系统内置</Tag> : <Tag color="blue">自定义</Tag>,
    },
    {
      title: "权限数",
      key: "perm_count",
      render: (_: unknown, record: RoleItem) => record.permissions?.length ?? 0,
    },
    { title: "描述", dataIndex: "description", key: "description", ellipsis: true },
    {
      title: "操作",
      key: "actions",
      render: (_: unknown, record: RoleItem) => (
        <div className="flex gap-2">
          <Button size="small" disabled={record.is_system} onClick={() => openEdit(record)}>
            编辑
          </Button>
          <Popconfirm
            title="确认删除该角色？"
            disabled={record.is_system}
            onConfirm={() => handleDelete(record)}
          >
            <Button size="small" danger disabled={record.is_system}>
              删除
            </Button>
          </Popconfirm>
        </div>
      ),
    },
  ]

  return (
    <div>
      <div className="mb-3">
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          新建角色
        </Button>
      </div>
      <Table rowKey="id" columns={columns} dataSource={roles} pagination={false} size="middle" />

      <Drawer
        title={editing === "new" ? "新建角色" : "编辑角色"}
        size={520}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        extra={
          <Button type="primary" loading={saving} onClick={handleSave}>
            保存
          </Button>
        }
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label="角色名称"
            rules={[{ required: true, message: "请输入角色名称" }]}
          >
            <Input placeholder="如：质量审核员" />
          </Form.Item>
          <Form.Item
            name="code"
            label="角色编码"
            rules={[{ required: true, message: "请输入角色编码" }]}
          >
            <Input placeholder="如：qa_auditor（小写字母/数字/下划线）" disabled={editing !== "new"} />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="角色职责说明（可选）" />
          </Form.Item>
        </Form>

        <div className="mt-2">
          <div className="text-sm font-medium mb-2">权限点</div>
          <div className="space-y-3 max-h-80 overflow-y-auto border rounded-md p-3">
            {permissionsByModule.map(([module, perms]) => (
              <div key={module}>
                <div className="text-xs font-semibold text-[var(--color-steel)] mb-1">{module}</div>
                <Checkbox.Group
                  value={selectedPerms}
                  onChange={(vals) => setSelectedPerms(vals as string[])}
                  options={perms.map((p) => ({
                    label: `${p.action} (${p.code})`,
                    value: p.code,
                  }))}
                  className="flex flex-wrap gap-x-4"
                />
              </div>
            ))}
          </div>
        </div>

        <div className="mt-4">
          <div className="text-sm font-medium mb-2">菜单权限</div>
          <div className="max-h-80 overflow-y-auto border rounded-md p-3">
            {editing !== "new" && editing && !menuLoading ? (
              <div className="text-xs text-[var(--color-stone)] mb-2">
                已勾选 {selectedMenuIds.length} 项（按钮节点勾选后其权限码并入用户权限）
              </div>
            ) : null}
            <Spin spinning={menuLoading} description="菜单加载中…">
              <Tree
                key="role-menu-tree"
                checkable
                checkedKeys={selectedMenuIds}
                onCheck={(keys) => setSelectedMenuIds(keys as string[])}
                treeData={menuTreeData}
                defaultExpandAll
                selectable={false}
                showLine={{ showLeafIcon: false }}
              />
            </Spin>
          </div>
        </div>

        <div className="mt-4">
          <div className="text-sm font-medium mb-2">可见部门（数据范围）</div>
          <div className="border rounded-md p-3">
            <DataScopeConfig
              departments={initialDepartments}
              value={dataScope}
              onChange={setDataScope}
            />
          </div>
        </div>
      </Drawer>
    </div>
  )
}