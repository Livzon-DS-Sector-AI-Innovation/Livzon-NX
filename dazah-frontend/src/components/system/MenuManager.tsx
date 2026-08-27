"use client"

import { useMemo, useState } from "react"
import {
  App,
  Button,
  Drawer,
  Form,
  Input,
  InputNumber,
  Popconfirm,
  Select,
  Space,
  Tag,
  Tree,
  TreeSelect,
  Typography,
} from "antd"
import type { TreeDataNode } from "antd"
import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  PlayCircleOutlined,
  StopOutlined,
} from "@ant-design/icons"
import type { MenuFlatItem, MenuTreeNode } from "@/lib/menu-tree"
import { buildMenuTree } from "@/lib/menu-tree"
import { createMenu, deleteMenu, updateMenu } from "@/actions/admin"

interface MenuManagerProps {
  initialMenus: MenuFlatItem[]
}

type MenuFormValues = {
  parent_id?: string | null
  name: string
  type: "directory" | "menu" | "button"
  permission_code?: string | null
  route_path?: string | null
  icon?: string | null
  sort_order?: number
  status: "active" | "disabled"
}

const TYPE_LABELS: Record<string, string> = {
  directory: "目录",
  menu: "菜单",
  button: "按钮",
}

const menuFormInitial: MenuFormValues = {
  name: "",
  type: "menu",
  sort_order: 0,
  status: "active",
}

export function MenuManager({ initialMenus }: MenuManagerProps) {
  const { message } = App.useApp()
  const [menus, setMenus] = useState<MenuFlatItem[]>(initialMenus)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editing, setEditing] = useState<MenuFlatItem | null>(null)
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm<MenuFormValues>()

  const treeData = useMemo(() => {
    const nodes = buildMenuTree(menus)
    const toTreeData = (children: ReturnType<typeof buildMenuTree>): TreeDataNode[] =>
      children.map((node) => {
        const isDisabled = node.status === "disabled"
        const title = (
          <div className="flex items-center gap-2 group">
            <Typography.Text type={isDisabled ? "secondary" : undefined} delete={isDisabled}>
              {node.name}
            </Typography.Text>
            <Tag color={node.type === "directory" ? "geekblue" : node.type === "button" ? "purple" : "blue"}>
              {TYPE_LABELS[node.type] ?? node.type}
            </Tag>
            {isDisabled && <Tag color="default">已禁用</Tag>}
            <span className="opacity-0 group-hover:opacity-100 transition-opacity flex gap-1">
              <Button
                size="small"
                type="text"
                icon={<PlusOutlined />}
                title="添加子节点"
                onClick={() => openCreate(node.id)}
              />
              <Button
                size="small"
                type="text"
                icon={<EditOutlined />}
                title="编辑"
                onClick={() => openEdit(node)}
              />
              {isDisabled ? (
                <Button
                  size="small"
                  type="text"
                  icon={<PlayCircleOutlined />}
                  title="启用"
                  onClick={() => toggleStatus(node, "active")}
                />
              ) : (
                <Button
                  size="small"
                  type="text"
                  icon={<StopOutlined />}
                  title="禁用"
                  onClick={() => toggleStatus(node, "disabled")}
                />
              )}
              <Popconfirm
                title="确认删除该菜单？"
                description="有子节点的菜单不能删除，只能禁用。"
                okText="删除"
                okButtonProps={{ danger: true }}
                onConfirm={() => handleDelete(node)}
              >
                <Button size="small" type="text" danger icon={<DeleteOutlined />} title="删除" />
              </Popconfirm>
            </span>
          </div>
        )
        return {
          key: node.id,
          title,
          children: node.children.length > 0 ? toTreeData(node.children) : undefined,
        }
      })
    return toTreeData(nodes)
  }, [menus])

  const openCreate = (parentId?: string) => {
    setEditing(null)
    form.setFieldsValue({ ...menuFormInitial, parent_id: parentId ?? null })
    setDrawerOpen(true)
  }

  const openEdit = (node: MenuTreeNode) => {
    const menu = menus.find((m) => m.id === node.id) ?? {
      id: node.id,
      key: node.key,
      parent_id: node.parentId,
      name: node.name,
      type: node.type,
      permission_code: node.permissionCode,
      route_path: node.routePath,
      component_path: null,
      icon: node.icon,
      sort_order: node.sortOrder,
      status: node.status,
    }
    setEditing(menu)
    form.setFieldsValue({
      parent_id: menu.parent_id ?? null,
      name: menu.name,
      type: menu.type as MenuFormValues["type"],
      permission_code: menu.permission_code ?? undefined,
      route_path: menu.route_path ?? undefined,
      icon: menu.icon ?? undefined,
      sort_order: menu.sort_order,
      status: menu.status as MenuFormValues["status"],
    })
    setDrawerOpen(true)
  }

  const handleSave = async () => {
    const values = await form.validateFields()
    setSaving(true)
    try {
      if (editing) {
        await updateMenu(editing.id, {
          name: values.name,
          type: values.type,
          permission_code: values.permission_code || null,
          route_path: values.route_path || null,
          icon: values.icon || null,
          sort_order: values.sort_order,
          status: values.status,
        })
        message.success("菜单已更新")
      } else {
        await createMenu({
          parent_id: values.parent_id ?? null,
          name: values.name,
          type: values.type,
          permission_code: values.permission_code || null,
          route_path: values.route_path || null,
          icon: values.icon || null,
          sort_order: values.sort_order ?? 0,
          status: values.status,
        })
        message.success("菜单已创建")
      }
      setDrawerOpen(false)
      window.location.reload()
    } catch (e) {
      message.error(e instanceof Error ? e.message : "保存失败")
    } finally {
      setSaving(false)
    }
  }

  const toggleStatus = async (menu: { id: string }, status: "active" | "disabled") => {
    try {
      await updateMenu(menu.id, { status })
      message.success(status === "active" ? "菜单已启用" : "菜单已禁用")
      window.location.reload()
    } catch (e) {
      message.error(e instanceof Error ? e.message : "操作失败")
    }
  }

  const handleDelete = async (menu: { id: string }) => {
    try {
      await deleteMenu(menu.id)
      message.success("菜单已删除")
      setMenus((prev) => prev.filter((m) => m.id !== menu.id))
    } catch (e) {
      message.error(e instanceof Error ? e.message : "删除失败")
    }
  }

  const parentTreeData = useMemo(() => {
    const toParentData = (children: ReturnType<typeof buildMenuTree>): TreeDataNode[] =>
      children
        .filter((n) => n.type === "directory" || n.type === "menu")
        .map((n) => ({
          key: n.id,
          title: n.name,
          children: n.children.length > 0 ? toParentData(n.children) : undefined,
        }))
    return toParentData(buildMenuTree(menus))
  }, [menus])

  return (
    <div>
      <div className="mb-3">
        <Button type="primary" icon={<PlusOutlined />} onClick={() => openCreate()}>
          新建菜单
        </Button>
      </div>
      <div className="border rounded-md p-4 bg-white max-h-[calc(100vh-260px)] overflow-y-auto">
        <Tree
          key="menu-tree"
          treeData={treeData}
          defaultExpandAll
          blockNode
          selectable={false}
          showLine={{ showLeafIcon: false }}
        />
      </div>

      <Drawer
        title={editing ? "编辑菜单" : "新建菜单"}
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
            label="名称"
            rules={[{ required: true, message: "请输入菜单名称" }]}
          >
            <Input placeholder="如：生产管理 / 批次管理 / 新增按钮" maxLength={100} />
          </Form.Item>
          <Form.Item
            name="type"
            label="类型"
            rules={[{ required: true, message: "请选择类型" }]}
          >
            <Select
              options={[
                { value: "directory", label: "目录（分组，不可跳转或可跳转父级）" },
                { value: "menu", label: "菜单（可跳转页面）" },
                { value: "button", label: "按钮（按钮级权限点）" },
              ]}
            />
          </Form.Item>
          <Form.Item name="parent_id" label={editing ? "父节点（留空为顶层）" : "所属父节点"}>
            <TreeSelect
              allowClear
              placeholder="顶层目录"
              treeData={parentTreeData}
              treeDefaultExpandAll
              disabled={!!editing}
            />
          </Form.Item>
          <Form.Item
            name="route_path"
            label="路由路径"
            rules={[
              {
                pattern: /^(\/[\w-]+)*\/?$/,
                message: "路径格式：/module/page（字母/数字/中划线）",
              },
            ]}
          >
            <Input placeholder="如：/production/batches（目录与按钮可留空）" maxLength={255} />
          </Form.Item>
          <Form.Item name="icon" label="图标名">
            <Input placeholder="如：factory / cog / shield（可留空）" maxLength={64} />
          </Form.Item>
          <Form.Item
            name="permission_code"
            label="权限码（按钮必填）"
            extra="格式：模块:资源:操作，如 hr:employee:create（小写字母/数字/下划线）"
            rules={[
              {
                pattern: /^[a-z][a-z0-9_]*(:[a-z][a-z0-9_]*){0,2}$/,
                message: "格式：模块[:资源[:操作]]",
              },
            ]}
          >
            <Input placeholder="如：hr:employee:create" maxLength={128} />
          </Form.Item>
          <Space size="large" className="w-full" styles={{ item: { flex: 1 } }}>
            <Form.Item name="sort_order" label="排序">
              <InputNumber min={0} className="w-full" />
            </Form.Item>
            <Form.Item name="status" label="状态">
              <Select
                options={[
                  { value: "active", label: "启用" },
                  { value: "disabled", label: "禁用" },
                ]}
              />
            </Form.Item>
          </Space>
        </Form>
      </Drawer>
    </div>
  )
}