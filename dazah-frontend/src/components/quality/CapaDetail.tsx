'use client'

import { useEffect, useState } from 'react'
import { useRouter, useParams } from 'next/navigation'
import { App, Button, Card, Descriptions, Form, Input, Select, Space } from 'antd'
import { ArrowLeftOutlined, DeleteOutlined, EditOutlined } from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import dayjs from 'dayjs'
import { fetchCapa } from '@/lib/api/client/quality'

import { deleteCapa, updateCapa } from '@/actions/quality-capa'

const { TextArea } = Input

// 台账「CAPA效果评估」列取值，与飞书台账口径一致
const EVALUATION_RESULT_OPTIONS = [
  { label: '有效', value: '有效' },
  { label: '无效', value: '无效' },
  { label: '进行中', value: '进行中' },
]

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

function formatDay(value: string | null | undefined): string {
  return value ? dayjs(value).format('YYYY-MM-DD') : '-'
}

/**
 * CAPA 台账详情：只展示和登记台账一致的列，并支持直接修改这些列。
 * 台账按登记口径维护，不承载平台内部流程，因此不再展示流程卡片与流程按钮。
 */
export function CapaDetail() {
  const router = useRouter()
  const params = useParams()
  const { message, modal } = App.useApp()
  const queryClient = useQueryClient()
  const id = params.id as string

  const { data: capa, isLoading: loading, error } = useQuery({
    queryKey: ['quality-capa', 'detail', id],
    queryFn: () => fetchCapa(id),
  })

  const [editMode, setEditMode] = useState(false)
  const [editForm] = Form.useForm()

  useEffect(() => {
    if (error) {
      message.error(getErrorMessage(error, '加载失败'))
      router.push('/quality/capas')
    }
  }, [error, message, router])

  const handleEdit = () => {
    if (!capa) return
    editForm.setFieldsValue({
      capa_code: capa.capa_code,
      expected_completion_date: capa.expected_completion_date
        ? dayjs(capa.expected_completion_date).format('YYYY-MM-DD')
        : null,
      department: capa.department,
      affected_product: capa.affected_product,
      source_code: capa.source_code,
      title: capa.title,
      evaluation_result: capa.evaluation_result,
      closure_date: capa.closure_date ? dayjs(capa.closure_date).format('YYYY-MM-DD') : null,
      qa_confirmer: capa.qa_confirmer,
      qa_confirm_date: capa.qa_confirm_date ? dayjs(capa.qa_confirm_date).format('YYYY-MM-DD') : null,
    })
    setEditMode(true)
  }

  const handleSaveEdit = async () => {
    try {
      const values = await editForm.validateFields()
      const result = await updateCapa(capa!.id, {
        ...values,
        expected_completion_date: values.expected_completion_date
          ? new Date(values.expected_completion_date).toISOString()
          : undefined,
        closure_date: values.closure_date ? new Date(values.closure_date).toISOString() : undefined,
        qa_confirm_date: values.qa_confirm_date
          ? new Date(values.qa_confirm_date).toISOString()
          : undefined,
      })
      message.success('保存成功')
      setEditMode(false)
      queryClient.invalidateQueries({ queryKey: ['quality-capa', 'detail', id] })
      queryClient.invalidateQueries({ queryKey: ['quality-capa'] })
    } catch (error: unknown) {
      if (error && typeof error === 'object' && 'errorFields' in error) return
      message.error(getErrorMessage(error, '保存失败'))
    }
  }

  const handleDelete = () => {
    modal.confirm({
      title: '确认删除',
      content: '确定要删除此CAPA吗？此操作不可恢复。',
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await deleteCapa(capa!.id)
          message.success('删除成功')
          router.push('/quality/capas')
        } catch (error: unknown) {
          message.error(getErrorMessage(error, '删除失败'))
        }
      },
    })
  }

  if (loading) {
    return <div>加载中...</div>
  }

  if (!capa) {
    return <div>未找到CAPA</div>
  }

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <Button icon={<ArrowLeftOutlined />} onClick={() => router.push('/quality/capas')}>
            返回
          </Button>
          <h2 style={{ margin: 0 }}>{capa.capa_code}</h2>
        </Space>
        <Space>
          {!editMode ? (
            <Button icon={<EditOutlined />} onClick={handleEdit}>
              编辑
            </Button>
          ) : (
            <>
              <Button onClick={() => setEditMode(false)}>取消</Button>
              <Button type="primary" onClick={handleSaveEdit}>
                保存
              </Button>
            </>
          )}
          <Button danger icon={<DeleteOutlined />} onClick={handleDelete}>
            删除
          </Button>
        </Space>
      </div>

      {!editMode ? (
        <Card title="基本信息" style={{ marginBottom: 16 }}>
          <Descriptions column={2}>
            <Descriptions.Item label="CAPA编号">{capa.capa_code || '-'}</Descriptions.Item>
            <Descriptions.Item label="启动日期">
              {formatDay(capa.expected_completion_date ?? capa.created_at)}
            </Descriptions.Item>
            <Descriptions.Item label="事件部门">{capa.department || '-'}</Descriptions.Item>
            <Descriptions.Item label="涉及产品">{capa.affected_product || '-'}</Descriptions.Item>
            <Descriptions.Item label="来源编号">{capa.source_code || '-'}</Descriptions.Item>
            <Descriptions.Item label="CAPA简述" span={2}>
              {capa.title || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="CAPA效果评估">{capa.evaluation_result || '-'}</Descriptions.Item>
            <Descriptions.Item label="关闭日期">
              {capa.closure_date
                ? dayjs(capa.closure_date).format('YYYY-MM-DD')
                : capa.evaluation_result === '进行中'
                  ? '进行中'
                  : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="QA质量员">{capa.qa_confirmer || '-'}</Descriptions.Item>
            <Descriptions.Item label="QA质量员确认日期">
              {formatDay(capa.qa_confirm_date)}
            </Descriptions.Item>
          </Descriptions>
        </Card>
      ) : (
        <Card title="编辑登记信息" style={{ marginBottom: 16 }}>
          <Form form={editForm} layout="vertical">
            <Form.Item
              name="capa_code"
              label="CAPA编号"
              rules={[{ required: true, message: '请输入CAPA编号' }]}
            >
              <Input />
            </Form.Item>
            <Form.Item name="expected_completion_date" label="启动日期">
              <Input type="date" />
            </Form.Item>
            <Form.Item name="department" label="事件部门">
              <Input />
            </Form.Item>
            <Form.Item name="affected_product" label="涉及产品">
              <Input />
            </Form.Item>
            <Form.Item name="source_code" label="来源编号">
              <Input />
            </Form.Item>
            <Form.Item
              name="title"
              label="CAPA简述"
              rules={[{ required: true, message: '请输入CAPA简述' }]}
            >
              <TextArea rows={3} />
            </Form.Item>
            <Form.Item name="evaluation_result" label="CAPA效果评估">
              <Select options={EVALUATION_RESULT_OPTIONS} allowClear />
            </Form.Item>
            <Form.Item name="closure_date" label="关闭日期">
              <Input type="date" />
            </Form.Item>
            <Form.Item name="qa_confirmer" label="QA质量员">
              <Input />
            </Form.Item>
            <Form.Item name="qa_confirm_date" label="QA质量员确认日期">
              <Input type="date" />
            </Form.Item>
          </Form>
        </Card>
      )}

      <Card
        title="关联CAPA计划"
        style={{ marginBottom: 16 }}
        extra={
          <Button
            type="link"
            style={{ padding: 0 }}
            onClick={() =>
              router.push(
                `/quality/capas/plans?${new URLSearchParams({ capa_code: capa.capa_code })}`,
              )
            }
          >
            查看计划跟踪
          </Button>
        }
      >
        {capa.linked_plan_contents && capa.linked_plan_contents.length > 0 ? (
          <div style={{ display: 'grid', gap: 8 }}>
            {capa.linked_plan_contents.map((plan, index) => (
              <div
                key={`${plan}-${index}`}
                style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', lineHeight: 1.6 }}
              >
                {plan}
              </div>
            ))}
          </div>
        ) : (
          '-'
        )}
      </Card>
    </div>
  )
}