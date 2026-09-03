"use client"

import { PAGE_DATA_SCOPE_VISIBLE } from "@/lib/page-permission-editor"

import { useMemo, useState } from "react"
import { Alert, App, Button, Card, Descriptions, Form, Select, Space, Tag, Typography } from "antd"
import type { AdminUserItem } from "@/lib/api/server/admin"
import { getUserPagePermissions, type UserPagePermissionsOut } from "@/actions/users"
import {
  simulatePagePermission,
  type PagePermissionSimulationOut,
} from "@/actions/admin"
import { PermissionRolloutManager } from "./PermissionRolloutManager"

const permissionNames = { access: "访问页面", query: "查询数据", operate: "操作业务" }
const scopeNames: Record<string, string> = {
  not_applicable: "不适用", department_tree: "本部门及下级",
  departments: "指定部门及下级", all: "全部部门", self: "仅本人",
}

export function PermissionVerification({ users }: { users: AdminUserItem[] }) {
  const { message } = App.useApp()
  const [form] = Form.useForm()
  const [userId, setUserId] = useState<string>()
  const [snapshot, setSnapshot] = useState<UserPagePermissionsOut | null>(null)
  const [result, setResult] = useState<PagePermissionSimulationOut | null>(null)
  const [loading, setLoading] = useState(false)

  const definitionByKey = useMemo(
    () => new Map((snapshot?.definitions || []).map((item) => [item.page_key, item])),
    [snapshot],
  )
  const selectedPageKey = Form.useWatch("page_key", form) as string | undefined
  const selectedDefinition = selectedPageKey ? definitionByKey.get(selectedPageKey) : undefined

  const selectUser = async (nextUserId: string) => {
    setUserId(nextUserId)
    setResult(null)
    form.resetFields(["page_key", "permission", "sensitive_action"])
    try {
      setSnapshot(await getUserPagePermissions(nextUserId))
    } catch (error) {
      message.error(error instanceof Error ? error.message : "页面权限快照加载失败")
    }
  }
  const simulate = async (values: {
    page_key: string
    permission: "access" | "query" | "operate"
    sensitive_action?: string
  }) => {
    if (!userId) return
    setLoading(true)
    try {
      setResult(await simulatePagePermission({ user_id: userId, ...values }))
    } catch (error) {
      message.error(error instanceof Error ? error.message : "模拟判定失败")
    } finally {
      setLoading(false)
    }
  }

  return <div className="space-y-4">
    <PermissionRolloutManager />
    <Card title="按页面验证生效权限" size="small">
      <Space direction="vertical" size="middle" className="w-full">
        <Select showSearch optionFilterProp="label" className="w-full max-w-md"
          placeholder="选择账号" value={userId} onChange={selectUser}
          options={users.map((user) => ({
            value: user.id, label: `${user.name}（${user.department || "未分配部门"}）`,
          }))} />
        <Form form={form} layout="vertical" onFinish={simulate} className="grid gap-3 lg:grid-cols-3">
          <Form.Item name="page_key" label="菜单页面" rules={[{ required: true, message: "请选择菜单页面" }]}>
            <Select showSearch optionFilterProp="label" disabled={!snapshot}
              options={(snapshot?.definitions || []).map((definition) => ({
                value: definition.page_key,
                label: definition.page_name,
              }))} onChange={() => form.setFieldValue("sensitive_action", undefined)} />
          </Form.Item>
          <Form.Item name="permission" label="业务动作" rules={[{ required: true, message: "请选择业务动作" }]}>
            <Select options={Object.entries(permissionNames).map(([value, label]) => ({ value, label }))} />
          </Form.Item>
          <Form.Item name="sensitive_action" label="高风险动作（可选）">
            <Select allowClear placeholder="普通业务动作" options={(selectedDefinition?.sensitive_actions || []).map(
              (action) => ({ value: action.key, label: action.name }),
            )} />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={loading} disabled={!userId}>
            模拟判定
          </Button>
        </Form>
        {result && <Alert type={result.allowed ? "success" : "error"} showIcon
          message={result.allowed ? "允许执行" : "拒绝执行"} description={result.reason} />}
      </Space>
    </Card>

    <Card title="当前页面生效结果" size="small">
      {snapshot ? <div className="space-y-3">
        {(snapshot.grants || []).length ? (snapshot.grants || []).map((grant) => {
          const definition = definitionByKey.get(grant.page_key)
          return <Descriptions key={grant.page_key} size="small" bordered column={1}
            title={definition?.page_name || "菜单页面"}>
            <Descriptions.Item label="权限">
              {(grant.permissions || []).length ? (grant.permissions || []).map((permission) =>
                <Tag key={permission} color="blue">{permissionNames[permission]}</Tag>,
              ) : <Tag>明确拒绝</Tag>}
            </Descriptions.Item>
            <Descriptions.Item label="来源">
              {grant.source === "role" ? grant.source_role_names?.join("、") || "角色基线" :
                grant.source === "user" ? "用户覆盖" : grant.source === "super_admin" ? "系统管理员" : "用户覆盖（拒绝）"}
            </Descriptions.Item>
            {PAGE_DATA_SCOPE_VISIBLE && <Descriptions.Item label="数据范围">
              {scopeNames[grant.data_scope.scope_type] || grant.data_scope.scope_type}
            </Descriptions.Item>}
          </Descriptions>
        }) : <Typography.Text type="secondary">该账号尚无新页面授权。</Typography.Text>}
      </div> : <Typography.Text type="secondary">请选择账号查看页面权限。</Typography.Text>}
    </Card>
  </div>
}
