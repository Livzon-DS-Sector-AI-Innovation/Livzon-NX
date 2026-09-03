"use client"

import { useState } from "react"
import { App, Button, Drawer, Form, Input, Popconfirm, Table, Tag } from "antd"
import { PlusOutlined } from "@ant-design/icons"
import type { PermissionItem, RoleItem } from "@/lib/api/client/admin"
import type { DepartmentItem } from "@/lib/api/server/admin"
import type { MenuFlatItem } from "@/lib/menu-tree"
import { createRole, deleteRole, updateRole } from "@/actions/admin"
import { RolePagePermissionsDrawer } from "./RolePagePermissionsDrawer"

interface RoleManagerProps {
  initialRoles: RoleItem[]
  initialPermissions?: PermissionItem[]
  initialMenus?: MenuFlatItem[]
  initialDepartments: DepartmentItem[]
}

export function RoleManager({ initialRoles, initialDepartments }: RoleManagerProps) {
  const { message } = App.useApp()
  const [roles, setRoles] = useState(initialRoles)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editing, setEditing] = useState<RoleItem | "new" | null>(null)
  const [pageRole, setPageRole] = useState<RoleItem | null>(null)
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm()

  const openCreate = () => {
    setEditing("new")
    form.resetFields()
    setDrawerOpen(true)
  }
  const openEdit = (role: RoleItem) => {
    setEditing(role)
    form.setFieldsValue(role)
    setDrawerOpen(true)
  }
  const save = async () => {
    const values = await form.validateFields()
    setSaving(true)
    try {
      if (editing === "new") {
        await createRole(values)
        message.success("角色已创建；请在页面权限中设置最小授权基线")
      } else if (editing) {
        await updateRole(editing.id, { name: values.name, description: values.description })
        message.success("角色信息已更新")
      }
      setDrawerOpen(false)
      window.location.reload()
    } catch (error) {
      message.error(error instanceof Error ? error.message : "保存失败")
    } finally {
      setSaving(false)
    }
  }
  const remove = async (role: RoleItem) => {
    try {
      await deleteRole(role.id)
      setRoles((current) => current.filter((item) => item.id !== role.id))
      message.success("角色已删除")
    } catch (error) {
      message.error(error instanceof Error ? error.message : "删除失败")
    }
  }

  return <div>
    <div className="mb-3"><Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
      新建角色
    </Button></div>
    <Table rowKey="id" dataSource={roles} pagination={false} scroll={{ x: 980 }} columns={[
      { title: "角色名称", dataIndex: "name", key: "name" },
      { title: "角色标识", dataIndex: "code", key: "code" },
      { title: "类型", dataIndex: "is_system", key: "is_system", render: (value: boolean) =>
        value ? <Tag color="gold">系统内置</Tag> : <Tag color="blue">自定义</Tag> },
      { title: "页面授权版本", dataIndex: "grant_version", key: "grant_version" },
      { title: "描述", dataIndex: "description", key: "description", ellipsis: true },
      { title: "操作", key: "actions", width: 260, fixed: "right", render: (_: unknown, role: RoleItem) => <div className="flex min-w-max gap-2">
        <Button size="small" disabled={role.code === "super_admin"} onClick={() => setPageRole(role)}>
          页面权限
        </Button>
        <Button size="small" disabled={role.is_system} onClick={() => openEdit(role)}>编辑信息</Button>
        <Popconfirm title="确认删除该角色？" disabled={role.is_system} onConfirm={() => remove(role)}>
          <Button size="small" danger disabled={role.is_system}>删除</Button>
        </Popconfirm>
      </div> },
    ]} />

    <Drawer title={editing === "new" ? "新建角色" : "编辑角色信息"} size={520}
      open={drawerOpen} onClose={() => setDrawerOpen(false)}
      extra={<Button type="primary" loading={saving} onClick={save}>保存</Button>}>
      <Form form={form} layout="vertical">
        <Form.Item name="name" label="角色名称" rules={[{ required: true, message: "请输入角色名称" }]}>
          <Input placeholder="如：质量审核员" />
        </Form.Item>
        <Form.Item name="code" label="角色标识" rules={[{ required: true, message: "请输入角色标识" }]}>
          <Input placeholder="如：qa_auditor" disabled={editing !== "new"} />
        </Form.Item>
        <Form.Item name="description" label="职责说明"><Input.TextArea rows={3} /></Form.Item>
      </Form>
    </Drawer>
    <RolePagePermissionsDrawer role={pageRole} departments={initialDepartments}
      open={Boolean(pageRole)} onClose={() => setPageRole(null)} />
  </div>
}
