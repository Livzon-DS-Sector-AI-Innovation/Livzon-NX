"use client"

import { useMemo, useState } from "react"
import {
  Alert,
  App,
  Button,
  Card,
  Descriptions,
  Form,
  Input,
  Select,
  Space,
  Spin,
  Tag,
  Tree,
  Typography,
} from "antd"
import { DownloadOutlined } from "@ant-design/icons"
import type { TreeDataNode } from "antd"
import type { AdminUserItem } from "@/lib/api/server/admin"
import type { MenuFlatItem } from "@/lib/menu-tree"
import { buildMenuTree, type MenuTreeNode } from "@/lib/menu-tree"
import {
  exportPermissions,
  previewUserPermission,
  simulatePermission,
  type PermissionPreviewData,
  type PermissionSimulateData,
} from "@/actions/admin"

interface PermissionVerificationProps {
  users: AdminUserItem[]
}

/** 常用接口示例路径（预填帮助） */
const EXAMPLE_PATHS = [
  { label: "HR 员工列表", path: "/api/v1/hr/employees" },
  { label: "质量偏差", path: "/api/v1/quality/deviations" },
]

export function PermissionVerification({ users }: PermissionVerificationProps) {
  const { message } = App.useApp()
  const [selectedUserId, setSelectedUserId] = useState<string>()
  const [preview, setPreview] = useState<PermissionPreviewData | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [simulateForm] = Form.useForm()
  const [simulateResult, setSimulateResult] = useState<PermissionSimulateData | null>(null)
  const [simulateLoading, setSimulateLoading] = useState(false)
  const [exporting, setExporting] = useState(false)

  const loadPreview = async (userId: string) => {
    setPreviewLoading(true)
    setPreview(null)
    setSimulateResult(null)
    try {
      const data = await previewUserPermission(userId)
      setPreview(data)
    } catch (e) {
      message.error(e instanceof Error ? e.message : "权限预览加载失败")
    } finally {
      setPreviewLoading(false)
    }
  }

  // 可见菜单树（扁平列表 → 树，复用项目唯一树构建器）
  const menuTreeData = useMemo<TreeDataNode[]>(() => {
    if (!preview) return []
    const toTreeData = (nodes: MenuTreeNode[]): TreeDataNode[] =>
      nodes.map((node) => ({
        key: node.id,
        title: node.name,
        children: node.children.length > 0 ? toTreeData(node.children) : undefined,
        disabled: node.status === "disabled",
      }))
    return toTreeData(buildMenuTree(preview.menus as MenuFlatItem[]))
  }, [preview])

  const handleSimulate = async (values: {
    method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' | 'HEAD'
    path: string
    department?: string
  }) => {
    if (!selectedUserId) {
      message.warning("请先选择账号")
      return
    }
    setSimulateLoading(true)
    try {
      const data = await simulatePermission({
        user_id: selectedUserId,
        method: values.method,
        path: values.path,
        department: values.department || null,
      })
      setSimulateResult(data)
    } catch (e) {
      message.error(e instanceof Error ? e.message : "模拟判定失败")
    } finally {
      setSimulateLoading(false)
    }
  }

  const handleExport = async () => {
    setExporting(true)
    try {
      const { filename, content } = await exportPermissions()
      const blob = new Blob([content], { type: "text/csv;charset=utf-8" })
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      message.success("权限清单已导出")
    } catch (e) {
      message.error(e instanceof Error ? e.message : "导出失败")
    } finally {
      setExporting(false)
    }
  }

  const formatTime = (iso: string) => {
    const d = new Date(iso)
    return Number.isNaN(d.getTime()) ? iso : d.toLocaleString("zh-CN", { hour12: false })
  }

  return (
    <div className="space-y-4">
      {/* 1. 账号选择 + 权限全景 */}
      <Card title="账号权限全景" size="small">
        <Space direction="vertical" size="middle" className="w-full">
          <Select
            showSearch
            placeholder="选择账号查看权限快照"
            style={{ width: 360 }}
            value={selectedUserId}
            onChange={(v) => {
              setSelectedUserId(v)
              loadPreview(v)
            }}
            optionFilterProp="label"
            options={users.map((u) => ({
              value: u.id,
              label: `${u.name}（${u.department ?? "未分配部门"}）`,
            }))}
          />
          <Spin spinning={previewLoading}>
            {preview ? (
              <div className="space-y-3">
                <div>
                  <div className="text-sm font-medium mb-1">角色</div>
                  <div className="flex flex-wrap gap-1">
                    {preview.roles.length === 0 ? (
                      <Tag>未分配角色</Tag>
                    ) : (
                      preview.roles.map((role) => (
                        <Tag
                          key={role.id}
                          color={
                            role.is_super_admin
                              ? "gold"
                              : role.source === "manual"
                                ? "blue"
                                : "green"
                          }
                        >
                          {role.name}
                          {role.is_super_admin
                            ? "（超级管理员·通配）"
                            : role.source === "manual"
                              ? "（手动分配）"
                              : "（部门映射）"}
                        </Tag>
                      ))
                    )}
                  </div>
                </div>
                <div>
                  <div className="text-sm font-medium mb-1">
                    权限点（{preview.permissions.length}）
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {preview.permissions.length === 0 ? (
                      <Tag>无权限点</Tag>
                    ) : (
                      preview.permissions.map((code) => <Tag key={code}>{code}</Tag>)
                    )}
                  </div>
                </div>
                <div>
                  <div className="text-sm font-medium mb-1">可见菜单</div>
                  <div className="border rounded-md p-3 max-h-72 overflow-auto">
                    {menuTreeData.length === 0 ? (
                      <Typography.Text type="secondary">无可见菜单</Typography.Text>
                    ) : (
                      <Tree
                        treeData={menuTreeData}
                        defaultExpandAll
                        selectable={false}
                        showLine={{ showLeafIcon: false }}
                      />
                    )}
                  </div>
                </div>
                <Descriptions size="small" column={1} bordered>
                  <Descriptions.Item label="数据范围">
                    {preview.data_scope.is_all
                      ? "全部部门"
                      : preview.data_scope.department_names.join("、") || "仅本部门及子部门"}
                  </Descriptions.Item>
                  <Descriptions.Item label="生效时间">
                    {formatTime(preview.effective_at)}
                  </Descriptions.Item>
                </Descriptions>
              </div>
            ) : (
              <Typography.Text type="secondary">
                {previewLoading ? "权限快照加载中…" : "请选择账号以查看权限快照"}
              </Typography.Text>
            )}
          </Spin>
        </Space>
      </Card>

      {/* 2. 接口准入模拟 */}
      <Card title="接口准入模拟" size="small">
        <Space direction="vertical" size="middle" className="w-full">
          <Form
            form={simulateForm}
            layout="inline"
            onFinish={handleSimulate}
            initialValues={{ method: "GET" }}
          >
            <Form.Item name="method" rules={[{ required: true, message: "请选择请求方法" }]}>
              <Select
                style={{ width: 110 }}
                options={["GET", "POST", "PUT", "DELETE"].map((m) => ({ value: m, label: m }))}
              />
            </Form.Item>
            <Form.Item
              name="path"
              rules={[{ required: true, message: "请输入接口路径" }]}
              style={{ minWidth: 320 }}
            >
              <Input placeholder="如 /api/v1/hr/employees" />
            </Form.Item>
            <Form.Item name="department">
              <Input placeholder="可选：部门（HR 数据范围参考）" style={{ width: 220 }} />
            </Form.Item>
            <Form.Item>
              <Button
                type="primary"
                htmlType="submit"
                loading={simulateLoading}
                disabled={!selectedUserId}
              >
                模拟判定
              </Button>
            </Form.Item>
          </Form>
          <div className="flex items-center gap-2">
            <span className="text-xs text-[var(--color-stone)]">预填示例：</span>
            {EXAMPLE_PATHS.map((item) => (
              <Button
                key={item.path}
                size="small"
                onClick={() => simulateForm.setFieldValue("path", item.path)}
              >
                {item.label}
              </Button>
            ))}
          </div>
          {simulateResult ? (
            <div className="space-y-2">
              <Alert
                type={simulateResult.allowed ? "success" : "error"}
                showIcon
                message={
                  <span>
                    <b>{simulateResult.allowed ? "允许访问" : "拒绝访问"}</b>
                    {!simulateResult.allowed && simulateResult.required ? (
                      <>
                        {" "}
                        — 缺失权限码{" "}
                        <Tag color="red" style={{ marginInlineEnd: 0 }}>
                          {simulateResult.required}
                        </Tag>
                      </>
                    ) : null}
                  </span>
                }
                description={simulateResult.reason}
              />
              {simulateResult.note ? (
                <Alert
                  type="warning"
                  showIcon
                  message="精校验标注"
                  description={simulateResult.note}
                />
              ) : null}
              {simulateResult.dept_scope_hint ? (
                <div className="text-xs text-[var(--color-stone)]">
                  部门范围参考：{simulateResult.dept_scope_hint}
                </div>
              ) : null}
            </div>
          ) : (
            <Typography.Text type="secondary">
              按指定账号的权限集合判定接口准入，结果与真实执行一致（不真实执行请求）。
            </Typography.Text>
          )}
        </Space>
      </Card>

      {/* 3. 导出权限清单 */}
      <Card title="导出权限清单" size="small">
        <Space direction="vertical" size="middle">
          <Button icon={<DownloadOutlined />} loading={exporting} onClick={handleExport}>
            导出权限清单
          </Button>
          <Typography.Text type="secondary" className="text-xs">
            导出全部角色与权限点的 CSV 清单（UTF-8 带 BOM，可用 Excel 直接打开）。
          </Typography.Text>
        </Space>
      </Card>
    </div>
  )
}
