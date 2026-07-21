'use client'

import { useCallback, useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { App, Button, Card, DatePicker, Descriptions, Form, Input, Modal, Select, Space, Table, Tag } from 'antd'
import { ArrowLeftOutlined, DeleteOutlined, EditOutlined, SyncOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import {
  createChangeActionPlan,
  deleteChange,
  deleteChangeActionPlan,
  syncChangeActionPlanToFeishu,
  syncChangeActionPlansFromFeishu,
  updateChange,
  updateChangeActionPlan,
} from '@/actions/quality'
import {
  fetchChange,
  fetchChangeActionPlansByChange,
} from '@/lib/api/quality'
import type { ChangeActionPlanListItem, ChangeDetail as ChangeDetailType } from '@/types/quality'
import { QualityAiPanel } from './QualityAiPanel'
import { ChangeActionPlanEditModal } from './change-action-plan-edit-modal'

const changeLevelOptions = [
  { label: '一级', value: '一级' },
  { label: '二级', value: '二级' },
  { label: '三级', value: '三级' },
]

function formatDate(value: string | null | undefined): string {
  if (!value) return '-'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
}

export function ChangeDetail() {
  const router = useRouter()
  const params = useParams()
  const { message, modal } = App.useApp()
  const [change, setChange] = useState<ChangeDetailType | null>(null)
  const [loading, setLoading] = useState(true)
  const [editorOpen, setEditorOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [plans, setPlans] = useState<ChangeActionPlanListItem[]>([])
  const [planLoading, setPlanLoading] = useState(false)
  const [planEditorOpen, setPlanEditorOpen] = useState(false)
  const [planSaving, setPlanSaving] = useState(false)
  const [editingPlan, setEditingPlan] = useState<ChangeActionPlanListItem | null>(null)
  const [form] = Form.useForm()

  const getErrorMessage = useCallback((error: unknown, fallback: string) => {
    if (error instanceof Error && error.message) {
      return error.message
    }
    return fallback
  }, [])

  const loadData = useCallback(async () => {
    try {
      const data = await fetchChange(params.id as string)
      setChange(data)
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '加载失败'))
      router.push('/quality/change')
    } finally {
      setLoading(false)
    }
  }, [getErrorMessage, message, params.id, router])

  useEffect(() => {
    void Promise.resolve().then(loadData)
  }, [loadData])

  const loadPlans = useCallback(async () => {
    if (!params.id) return
    try {
      setPlanLoading(true)
      const data = await fetchChangeActionPlansByChange(params.id as string)
      setPlans(data)
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '加载变更计划失败'))
    } finally {
      setPlanLoading(false)
    }
  }, [getErrorMessage, message, params.id])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadPlans()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [loadPlans])

  const handleOpenEdit = useCallback(() => {
    if (!change) return
    form.setFieldsValue({
      serial_number: change.serial_number,
      change_code: change.change_code,
      applicant_department: change.applicant_department,
      change_object: change.change_object,
      change_content: change.change_content,
      impact_assessment: change.impact_assessment,
      change_level: change.change_level,
      application_date: change.application_date ? dayjs(change.application_date) : null,
      planned_approval_date: change.planned_approval_date ? dayjs(change.planned_approval_date) : null,
      execution_date: change.execution_date ? dayjs(change.execution_date) : null,
      closure_date: change.closure_date ? dayjs(change.closure_date) : null,
    })
    setEditorOpen(true)
  }, [change, form])

  const handleSave = useCallback(async () => {
    if (!change) return
    try {
      const values = await form.validateFields()
      setSaving(true)
      await updateChange(change.id, {
        ...values,
        application_date: values.application_date ? values.application_date.format('YYYY-MM-DD') : null,
        planned_approval_date: values.planned_approval_date ? values.planned_approval_date.format('YYYY-MM-DD') : null,
        execution_date: values.execution_date ? values.execution_date.format('YYYY-MM-DD') : null,
        closure_date: values.closure_date ? values.closure_date.format('YYYY-MM-DD') : null,
      })
      message.success('保存成功')
      setEditorOpen(false)
      await loadData()
    } catch (error: unknown) {
      if (error && typeof error === 'object' && 'errorFields' in error) return
      message.error(getErrorMessage(error, '保存失败'))
    } finally {
      setSaving(false)
    }
  }, [change, form, getErrorMessage, loadData, message])

  const handleDelete = useCallback(() => {
    if (!change) return
    modal.confirm({
      title: '确认删除',
      content: `确定要删除变更 "${change.change_code}" 吗？`,
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await deleteChange(change.id)
          message.success('删除成功')
          router.push('/quality/change')
        } catch (error: unknown) {
          message.error(getErrorMessage(error, '删除失败'))
        }
      },
    })
  }, [change, getErrorMessage, message, modal, router])

  const handleSyncPlans = useCallback(async () => {
    try {
      const result = await syncChangeActionPlansFromFeishu()
      message.success(`同步完成：成功 ${result.synced} 条，失败 ${result.failed} 条`)
      await loadPlans()
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '同步飞书失败'))
    }
  }, [getErrorMessage, loadPlans, message])

  const handlePlanSubmit = useCallback(async (values: Record<string, unknown>) => {
    if (!change) return
    try {
      setPlanSaving(true)
      const payload = {
        ...values,
        change_id: change.id,
        change_code: String(values.change_code || change.change_code),
      }
      if (editingPlan) {
        await updateChangeActionPlan(editingPlan.id, payload)
        message.success('变更计划已更新')
      } else {
        await createChangeActionPlan(payload)
        message.success('变更计划已创建')
      }
      setPlanEditorOpen(false)
      setEditingPlan(null)
      await loadPlans()
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '保存变更计划失败'))
    } finally {
      setPlanSaving(false)
    }
  }, [change, editingPlan, getErrorMessage, loadPlans, message])

  const handlePlanDelete = useCallback((record: ChangeActionPlanListItem) => {
    modal.confirm({
      title: '确认删除',
      content: `确定要删除变更计划 "${record.project_name}" 吗？`,
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await deleteChangeActionPlan(record.id)
          message.success('变更计划已删除')
          await loadPlans()
        } catch (error: unknown) {
          message.error(getErrorMessage(error, '删除变更计划失败'))
        }
      },
    })
  }, [getErrorMessage, loadPlans, message, modal])

  const handlePlanSyncSingle = useCallback(async (record: ChangeActionPlanListItem) => {
    try {
      await syncChangeActionPlanToFeishu(record.id)
      message.success('已回写飞书')
      await loadPlans()
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '回写飞书失败'))
    }
  }, [getErrorMessage, loadPlans, message])

  const planColumns = [
    { title: '项目名称', dataIndex: 'project_name', width: 180 },
    { title: '涉及工作', dataIndex: 'related_work', width: 240, render: (value: string | null) => value || '-' },
    { title: '总负责人', dataIndex: 'owner_name', width: 120, render: (value: string | null) => value || '-' },
    { title: '部门总监', dataIndex: 'director_name', width: 120, render: (value: string | null) => value || '-' },
    { title: '项目截止时间', dataIndex: 'deadline_date', width: 140, render: formatDate },
    { title: '状态', dataIndex: 'status', width: 120, render: (value: string | null) => value || '-' },
    { title: '延期', dataIndex: 'delay_flag', width: 100, render: (value: string | null) => value || '-' },
    { title: '延期后日期', dataIndex: 'delayed_deadline_date', width: 140, render: formatDate },
    {
      title: '同步状态',
      key: 'sync_status',
      width: 120,
      render: (_: unknown, record: ChangeActionPlanListItem) => {
        const color = record.sync_status === 'synced' ? 'green' : record.sync_status === 'failed' ? 'red' : 'gold'
        const label = record.sync_status === 'synced' ? '已同步' : record.sync_status === 'failed' ? '同步失败' : '待同步'
        return <Tag color={color}>{label}</Tag>
      },
    },
    {
      title: '操作',
      key: 'action',
      width: 180,
      fixed: 'right' as const,
      render: (_: unknown, record: ChangeActionPlanListItem) => (
        <Space>
          <Button type="text" icon={<EditOutlined />} onClick={() => { setEditingPlan(record); setPlanEditorOpen(true) }} />
          <Button type="text" icon={<SyncOutlined />} onClick={() => handlePlanSyncSingle(record)} />
          <Button type="text" danger icon={<DeleteOutlined />} onClick={() => handlePlanDelete(record)} />
        </Space>
      ),
    },
  ]

  if (loading) return <div>加载中...</div>
  if (!change) return <div>未找到变更</div>

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <Button icon={<ArrowLeftOutlined />} onClick={() => router.push('/quality/change')}>
            返回
          </Button>
          <h2 style={{ margin: 0 }}>{change.change_code}</h2>
          <Tag color="blue">{change.change_level || '未定级'}</Tag>
        </Space>
        <Space>
          <Button icon={<EditOutlined />} onClick={handleOpenEdit}>
            编辑
          </Button>
          <Button danger icon={<DeleteOutlined />} onClick={handleDelete}>
            删除
          </Button>
        </Space>
      </div>

      <div style={{ marginBottom: 16 }}>
        <QualityAiPanel entityType="change" entityId={change.id} onApplied={loadData} />
      </div>

      <Card title="变更基础信息">
        <Descriptions column={2} bordered>
          <Descriptions.Item label="序号">{change.serial_number || '-'}</Descriptions.Item>
          <Descriptions.Item label="变更控制号">{change.change_code}</Descriptions.Item>
          <Descriptions.Item label="申请部门">{change.applicant_department || '-'}</Descriptions.Item>
          <Descriptions.Item label="变更等级">{change.change_level || '-'}</Descriptions.Item>
          <Descriptions.Item label="变更对象">{change.change_object || '-'}</Descriptions.Item>
          <Descriptions.Item label="申请日期">{formatDate(change.application_date)}</Descriptions.Item>
          <Descriptions.Item label="计划批准日期">{formatDate(change.planned_approval_date)}</Descriptions.Item>
          <Descriptions.Item label="正式执行日期">{formatDate(change.execution_date)}</Descriptions.Item>
          <Descriptions.Item label="关闭日期">{formatDate(change.closure_date)}</Descriptions.Item>
          <Descriptions.Item label="创建时间">{formatDate(change.created_at)}</Descriptions.Item>
          <Descriptions.Item label="变更内容" span={2}>
            <div style={{ whiteSpace: 'pre-wrap' }}>{change.change_content || '-'}</div>
          </Descriptions.Item>
          <Descriptions.Item label="影响评估" span={2}>
            <div style={{ whiteSpace: 'pre-wrap' }}>{change.impact_assessment || '-'}</div>
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card
        title="变更计划"
        style={{ marginTop: 16 }}
        extra={
          <Space>
            <Button icon={<SyncOutlined />} onClick={handleSyncPlans}>
              同步飞书
            </Button>
            <Button type="primary" onClick={() => { setEditingPlan(null); setPlanEditorOpen(true) }}>
              新增变更计划
            </Button>
          </Space>
        }
      >
        <Table
          rowKey="id"
          loading={planLoading}
          pagination={false}
          dataSource={plans}
          columns={planColumns}
          scroll={{ x: 1500 }}
        />
      </Card>

      <Modal
        title="编辑变更"
        open={editorOpen}
        onCancel={() => setEditorOpen(false)}
        onOk={handleSave}
        confirmLoading={saving}
        destroyOnHidden
        width={760}
      >
        <Form form={form} layout="vertical">
          <Form.Item label="序号" name="serial_number">
            <Input />
          </Form.Item>
          <Form.Item label="变更控制号" name="change_code" rules={[{ required: true, message: '请输入变更控制号' }]}>
            <Input />
          </Form.Item>
          <Form.Item label="变更申请部门" name="applicant_department">
            <Input />
          </Form.Item>
          <Form.Item label="变更对象" name="change_object">
            <Input />
          </Form.Item>
          <Form.Item label="变更内容" name="change_content">
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item label="影响评估" name="impact_assessment">
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item label="变更等级" name="change_level">
            <Select allowClear options={changeLevelOptions} />
          </Form.Item>
          <Form.Item label="申请日期" name="application_date">
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="计划批准日期" name="planned_approval_date">
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="正式执行日期" name="execution_date">
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="关闭日期" name="closure_date">
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>

      <ChangeActionPlanEditModal
        open={planEditorOpen}
        saving={planSaving}
        changeCode={change.change_code}
        initialValue={editingPlan}
        onCancel={() => {
          setPlanEditorOpen(false)
          setEditingPlan(null)
        }}
        onSubmit={handlePlanSubmit}
      />
    </div>
  )
}
