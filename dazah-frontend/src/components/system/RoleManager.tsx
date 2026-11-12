"use client"

import { useState } from "react"
import Link, { useLinkStatus } from "next/link"
import { App, Button, Drawer, Form, Input, Popconfirm, Table, Tag } from "antd"
import { PlusOutlined } from "@ant-design/icons"
import type { PermissionItem, RoleItem } from "@/lib/api/client/admin"
import type { MenuFlatItem } from "@/lib/menu-tree"
import { createRole, deleteRole, updateRole } from "@/actions/admin"
import {
  ROLE_CODE_MAX_LENGTH, ROLE_NAME_MAX_LENGTH, roleCodeError, roleNameError, trimRoleWhitespace,
} from "@/lib/role-creation"
import type { components } from "@/types/generated/schema"
import { rolePagePermissionsPath, type PermissionWorkbenchOrigin } from "@/lib/rolePagePermissionsPath"
import { roleTagColor } from "@/lib/role-tag"
import styles from "./RolePagePermissionsWorkbench.module.css"

type RoleFormValues = components["schemas"]["RoleCreateRequest"]

function PagePermissionLinkLabel() {
  const { pending } = useLinkStatus()
  return <span className={styles.openLinkLabel}>
    页面权限
    {pending && <span className={styles.openProgress} role="status" aria-label="正在打开页面权限" />}
  </span>
}

interface RoleManagerProps {
  initialRoles: RoleItem[]
  initialPermissions?: PermissionItem[]
  initialMenus?: MenuFlatItem[]
  origin?: PermissionWorkbenchOrigin
}

export function RoleManager({ initialRoles: roles, origin }: RoleManagerProps) {
  const { message } = App.useApp()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editing, setEditing] = useState<RoleItem | "new" | null>(null)
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm<RoleFormValues>()
  const creating = editing === "new"

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
  const save = async (values: RoleFormValues) => {
    if (saving) return
    setSaving(true)
    try {
      if (creating) {
        const result = await createRole({
          ...values,
          name: trimRoleWhitespace(values.name),
          code: trimRoleWhitespace(values.code),
        })
        if (!result.ok) {
          if (result.status === 409) {
            form.setFields([{ name: "code", errors: [result.message] }])
          } else {
            message.error(result.message)
          }
          return
        }
        message.success("角色已创建；请在页面权限中设置最小授权基线")
      } else if (editing) {
        await updateRole(editing.id, { name: values.name, description: values.description })
        message.success("角色信息已更新")
      }
      setDrawerOpen(false)
    } catch (error) {
      message.error(error instanceof Error ? error.message : "保存失败")
    } finally {
      setSaving(false)
    }
  }
  const remove = async (role: RoleItem) => {
    try {
      await deleteRole(role.id)
      message.success("角色已删除")
    } catch (error) {
      message.error(error instanceof Error ? error.message : "删除失败")
    }
  }

  return <div>
    <div className="mb-3"><Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
      新建角色
    </Button></div>
    <Table rowKey="id" dataSource={roles} tableLayout="fixed" scroll={{ x: 900 }}
      pagination={{ pageSize: 20, showSizeChanger: false }} columns={[
      { title: "角色名称", dataIndex: "name", key: "name", width: 120, ellipsis: true },
      { title: "角色标识", dataIndex: "code", key: "code", width: 180, ellipsis: true },
      { title: "类型", dataIndex: "is_system", key: "is_system", width: 110, render: (value: boolean, role: RoleItem) => {
        const label = role.code === "super_admin" ? "系统管理员"
          : role.code === "ordinary_admin" ? "普通管理员" : value ? "系统内置" : "自定义"
        return <Tag color={roleTagColor(role.code, value)}>{label}</Tag>
      } },
      { title: "页面授权版本", dataIndex: "grant_version", key: "grant_version", width: 120 },
      { title: "描述", dataIndex: "description", key: "description", ellipsis: true,
        render: (description: RoleItem["description"], role: RoleItem) =>
          role.is_system && role.code !== "super_admin" && role.code !== "ordinary_admin"
            ? "系统内置角色，可编辑" : description },
      { title: "操作", key: "actions", width: 240, fixed: "right", render: (_: unknown, role: RoleItem) => <div className="flex min-w-max gap-2">
        {role.code === "super_admin" || role.code === "ordinary_admin"
          ? <Button size="small" disabled>页面权限</Button>
          : <Link className={styles.openLink} href={rolePagePermissionsPath(role.id, origin)}>
              <PagePermissionLinkLabel />
            </Link>}
        <Button size="small" disabled={role.code === "super_admin" || role.code === "ordinary_admin"} onClick={() => openEdit(role)}>编辑信息</Button>
        <Popconfirm title={`确认删除角色“${role.name}”？`} description="删除后，该角色将不再为用户提供授权。"
          disabled={role.code === "super_admin" || role.code === "ordinary_admin"} onConfirm={() => remove(role)}>
          <Button size="small" danger disabled={role.code === "super_admin" || role.code === "ordinary_admin"}>删除</Button>
        </Popconfirm>
      </div> },
    ]} />

    <Drawer title={creating ? "新建角色" : "编辑角色信息"} size={520}
      open={drawerOpen} onClose={() => { if (!saving) setDrawerOpen(false) }}
      extra={<Button type="primary" loading={saving} onClick={() => form.submit()}>保存</Button>}>
      <Form form={form} layout="vertical" disabled={saving} onFinish={save}>
        <Form.Item name="name" label="角色名称" required
          extra={creating && `1–${ROLE_NAME_MAX_LENGTH} 个字符，支持中文和数字。自动去除首尾空白，中间不能有空白。`}
          rules={creating ? [{ validator: async (_, value: unknown) => {
            const error = roleNameError(value)
            if (error) throw new Error(error)
          } }] : [{ required: true, message: "请输入角色名称" }]}>
          <Input placeholder="如：质量审核员" />
        </Form.Item>
        <Form.Item name="code" label="角色标识" required
          extra={creating && `1–${ROLE_CODE_MAX_LENGTH} 个字符，限英文字母、数字和 _ . : -，不能与未删除的角色重复。自动去除首尾空白，中间不能有空白。`}
          rules={creating ? [{ validator: async (_, value: unknown) => {
            const error = roleCodeError(value)
            if (error) throw new Error(error)
          } }] : [{ required: true, message: "请输入角色标识" }]}>
          <Input placeholder="如：qa_auditor" disabled={!creating || saving} />
        </Form.Item>
        <Form.Item name="description" label="职责说明"><Input.TextArea rows={3} /></Form.Item>
      </Form>
    </Drawer>
  </div>
}
