'use client'

import { useCallback, useEffect, useState } from 'react'
import {
  App,
  Button,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import {
  createAgentSkill,
  deleteAgentSkill,
  disableAgentSkill,
  enableAgentSkill,
  getAgentSkills,
  updateAgentSkill,
  type AgentSkill,
} from '@/actions/agent-skills'

const { Text } = Typography
const { TextArea } = Input

const statusOptions = [
  { value: 'active', label: '启用' },
  { value: 'disabled', label: '停用' },
]

function splitKeywords(value: string | undefined): string[] {
  return (value || '')
    .split(/[,，\n]/)
    .map((item) => item.trim())
    .filter(Boolean)
}

export default function AgentSkillManagementClient() {
  const { message } = App.useApp()
  const [skills, setSkills] = useState<AgentSkill[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingSkill, setEditingSkill] = useState<AgentSkill | null>(null)
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm()

  const loadSkills = useCallback(async () => {
    setLoading(true)
    try {
      setSkills(await getAgentSkills())
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载 Skill 失败')
    } finally {
      setLoading(false)
    }
  }, [message])

  useEffect(() => {
    void Promise.resolve().then(loadSkills)
  }, [loadSkills])

  const handleCreate = () => {
    setEditingSkill(null)
    form.resetFields()
    form.setFieldsValue({ status: 'active' })
    setModalOpen(true)
  }

  const handleEdit = (record: AgentSkill) => {
    setEditingSkill(record)
    form.setFieldsValue({
      name: record.name,
      title: record.title,
      description: record.description,
      trigger_keywords: record.trigger_keywords.join('，'),
      content: record.content,
      status: record.status,
    })
    setModalOpen(true)
  }

  const handleSave = async () => {
    try {
      const values = await form.validateFields()
      setSaving(true)
      const payload = {
        title: values.title,
        description: values.description,
        trigger_keywords: splitKeywords(values.trigger_keywords),
        content: values.content,
        status: values.status,
      }
      if (editingSkill) {
        await updateAgentSkill(editingSkill.id, payload)
        message.success('Skill 已更新')
      } else {
        await createAgentSkill({
          name: values.name,
          ...payload,
          is_builtin: false,
        })
        message.success('Skill 已创建')
      }
      setModalOpen(false)
      loadSkills()
    } catch (error) {
      if (error instanceof Error) message.error(error.message)
    } finally {
      setSaving(false)
    }
  }

  const handleToggle = async (record: AgentSkill) => {
    try {
      if (record.status === 'active') {
        await disableAgentSkill(record.id)
        message.success('Skill 已停用')
      } else {
        await enableAgentSkill(record.id)
        message.success('Skill 已启用')
      }
      loadSkills()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '操作失败')
    }
  }

  const handleDelete = async (record: AgentSkill) => {
    try {
      await deleteAgentSkill(record.id)
      message.success('Skill 已删除')
      loadSkills()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '删除失败')
    }
  }

  const columns = [
    {
      title: 'Skill',
      key: 'skill',
      width: 260,
      render: (_: unknown, record: AgentSkill) => (
        <div>
          <div className="font-medium text-[var(--color-charcoal)]">{record.title}</div>
          <Text className="text-[12px] text-[var(--color-steel)]">{record.name}</Text>
        </div>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (status: string) => (
        <Tag color={status === 'active' ? 'success' : 'default'}>
          {status === 'active' ? '启用' : '停用'}
        </Tag>
      ),
    },
    {
      title: '类型',
      dataIndex: 'is_builtin',
      width: 100,
      render: (isBuiltin: boolean) => (
        <Tag color={isBuiltin ? 'purple' : 'blue'}>{isBuiltin ? '内置' : '自定义'}</Tag>
      ),
    },
    {
      title: '触发词',
      dataIndex: 'trigger_keywords',
      render: (keywords: string[]) => (
        <Space wrap size={[4, 4]}>
          {keywords.map((keyword) => (
            <Tag key={keyword}>{keyword}</Tag>
          ))}
        </Space>
      ),
    },
    {
      title: '版本',
      dataIndex: 'version',
      width: 80,
    },
    {
      title: '操作',
      key: 'actions',
      width: 220,
      fixed: 'right' as const,
      render: (_: unknown, record: AgentSkill) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>
            编辑
          </Button>
          <Button size="small" onClick={() => handleToggle(record)}>
            {record.status === 'active' ? '停用' : '启用'}
          </Button>
          <Popconfirm
            title="确认删除该 Skill？"
            disabled={record.is_builtin}
            onConfirm={() => handleDelete(record)}
            okText="确定"
            cancelText="取消"
          >
            <Button
              size="small"
              danger
              icon={<DeleteOutlined />}
              disabled={record.is_builtin}
            />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h2 className="m-0 text-[20px] font-semibold text-[var(--color-charcoal)]">
            Livzon Skill 管理
          </h2>
          <Text className="text-[13px] text-[var(--color-steel)]">
            管理助手渐进式披露的 Skill。普通用户只能使用，不能创建或修改。
          </Text>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={loadSkills}>
            刷新
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleCreate}>
            新建 Skill
          </Button>
        </Space>
      </div>

      <Table
        columns={columns}
        dataSource={skills}
        rowKey="id"
        loading={loading}
        scroll={{ x: 1080 }}
        pagination={{ pageSize: 10 }}
      />

      <Modal
        title={editingSkill ? '编辑 Skill' : '新建 Skill'}
        open={modalOpen}
        onOk={handleSave}
        onCancel={() => setModalOpen(false)}
        confirmLoading={saving}
        okText="保存"
        cancelText="取消"
        width={760}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="name" label="名称" rules={[{ required: !editingSkill }]}>
            <Input disabled={!!editingSkill} placeholder="livzon-workflow-builder" />
          </Form.Item>
          <Form.Item name="title" label="标题" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="description" label="描述" rules={[{ required: true }]}>
            <TextArea rows={3} />
          </Form.Item>
          <Form.Item name="trigger_keywords" label="触发词">
            <TextArea rows={2} placeholder="使用逗号或换行分隔" />
          </Form.Item>
          <Form.Item name="content" label="Skill 内容" rules={[{ required: true }]}>
            <TextArea rows={12} />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select options={statusOptions} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
