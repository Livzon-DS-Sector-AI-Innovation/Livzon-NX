"use client"

import { useState } from "react"
import { App, Button, Form, Input, Popconfirm, Select, Table, Tag } from "antd"
import { PlusOutlined } from "@ant-design/icons"
import type { DeptRuleItem, RoleItem } from "@/lib/api/client/admin"
import { createDeptRule, deleteDeptRule } from "@/actions/admin"

interface DeptRoleMapperProps {
  initialRules: DeptRuleItem[]
  initialRoles: RoleItem[]
  initialDepartments: unknown[]
}

type RuleFormValues = {
  role_id: string
  feishu_department_id?: string
  department_name?: string
}

export function DeptRoleMapper({ initialRules, initialRoles }: DeptRoleMapperProps) {
  const { message } = App.useApp()
  const [rules, setRules] = useState<DeptRuleItem[]>(initialRules)
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm<RuleFormValues>()

  const handleCreate = async () => {
    const values = await form.validateFields()
    if (!values.feishu_department_id && !values.department_name) {
      message.error("飞书部门 ID 与部门名至少填一个")
      return
    }
    setSaving(true)
    try {
      await createDeptRule({
        role_id: values.role_id,
        feishu_department_id: values.feishu_department_id || null,
        department_name: values.department_name || null,
      })
      message.success("映射规则已创建")
      form.resetFields()
      window.location.reload()
    } catch (e) {
      message.error(e instanceof Error ? e.message : "创建失败")
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (rule: DeptRuleItem) => {
    try {
      await deleteDeptRule(rule.id)
      message.success("规则已删除")
      setRules((prev) => prev.filter((r) => r.id !== rule.id))
    } catch (e) {
      message.error(e instanceof Error ? e.message : "删除失败")
    }
  }

  const columns = [
    {
      title: "角色",
      dataIndex: "role_name",
      key: "role_name",
      render: (v: string | undefined, record: DeptRuleItem) =>
        v ? <Tag color="blue">{v}</Tag> : record.role_code ?? "-",
    },
    { title: "飞书部门 ID", dataIndex: "feishu_department_id", key: "feishu_department_id" },
    { title: "部门名称", dataIndex: "department_name", key: "department_name" },
    {
      title: "操作",
      key: "actions",
      render: (_: unknown, record: DeptRuleItem) => (
        <Popconfirm title="确认删除该映射规则？" onConfirm={() => handleDelete(record)}>
          <Button size="small" danger>
            删除
          </Button>
        </Popconfirm>
      ),
    },
  ]

  return (
    <div className="space-y-4">
      <Form form={form} layout="inline" className="flex flex-wrap gap-2">
        <Form.Item
          name="role_id"
          rules={[{ required: true, message: "请选择角色" }]}
        >
          <Select
            placeholder="选择角色"
            style={{ width: 220 }}
            options={initialRoles.map((r) => ({ value: r.id, label: `${r.name}（${r.code}）` }))}
          />
        </Form.Item>
        <Form.Item name="feishu_department_id">
          <Input placeholder="飞书部门 ID（如 od-xxx）" style={{ width: 220 }} />
        </Form.Item>
        <Form.Item name="department_name">
          <Input placeholder="部门名称（如 质量管理部）" style={{ width: 220 }} />
        </Form.Item>
        <Button type="primary" icon={<PlusOutlined />} loading={saving} onClick={handleCreate}>
          新增规则
        </Button>
      </Form>

      <Table rowKey="id" columns={columns} dataSource={rules} pagination={false} size="middle" />
    </div>
  )
}