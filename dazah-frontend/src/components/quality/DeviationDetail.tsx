'use client'

import { useEffect, useState } from 'react'
import { useRouter, useParams } from 'next/navigation'
import { Alert, App, Card, Button, Space, Form, Input, Select, DatePicker, Radio } from 'antd'
import { ArrowLeftOutlined, DeleteOutlined } from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import dayjs from 'dayjs'
import { fetchDeviation } from '@/lib/api/client/quality'
import { updateDeviation, deleteDeviation } from '@/actions/quality-deviation'
import type { DeviationDetail as DeviationDetailType, DeviationStatus } from '@/types/quality'
import { useDeviationPermissions } from './useDeviationPermissions'

/** JSON 列视图类型：后端以 JSON 存储（generated 类型为 unknown[]），此处补充视图层类型 */
type DeviationJsonView = Omit<DeviationDetailType, 'investigation_records' | 'review_opinions'> & {
  investigation_records?: unknown[] | null
  review_opinions?: unknown[] | null
}

const { TextArea } = Input

const STATUS_LABELS: Record<DeviationStatus, string> = {
  draft: '草稿',
  pending_ai_analysis: '待AI分析',
  pending_investigation: '待调查',
  pending_dept_head_review: '待部门主管审核',
  pending_cross_dept_head_review: '待跨部门主管审核',
  pending_qa_review: '待QA审核',
  pending_qa_head_review: '待QA主管审核',
  pending_quality_head_review: '待质量主管审核',
  pending_final_code: '待最终编号',
  returned: '已退回',
  closed: '已关闭',
  cancelled: '已取消',
}

const STATUS_COLORS: Record<DeviationStatus, string> = {
  draft: 'default',
  pending_ai_analysis: 'purple',
  pending_investigation: 'blue',
  pending_dept_head_review: 'orange',
  pending_cross_dept_head_review: 'orange',
  pending_qa_review: 'orange',
  pending_qa_head_review: 'orange',
  pending_quality_head_review: 'orange',
  pending_final_code: 'cyan',
  returned: 'red',
  closed: 'green',
  cancelled: 'default',
}

const LEVEL_OPTIONS = [
  { label: '次要偏差', value: 'minor' },
  { label: '中等偏差', value: 'moderate' },
  { label: '严重偏差', value: 'major' },
]

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

interface DeviationDetailProps {
  initialDeviation?: DeviationDetailType | null
  initialLoadError?: string | null
  initialEditMode?: boolean
  saveAction?: ((formData: FormData) => Promise<void>) | undefined
}

export function DeviationDetail(props: DeviationDetailProps = {}) {
  const router = useRouter()
  const params = useParams()
  const { message, modal } = App.useApp()
  const queryClient = useQueryClient()
  const id = params.id as string
  const { canQuery, canOperate, canDelete, workflowFieldsReadOnly, authorizationKey } = useDeviationPermissions()
  const [initialAuthorizationKey] = useState(authorizationKey)

  const { data: deviation, isLoading: loading, error } = useQuery<DeviationJsonView>({
    queryKey: ['quality-deviation', 'detail', id, authorizationKey],
    queryFn: () => fetchDeviation(id),
    enabled: !!id && canQuery,
    initialData: canQuery && initialAuthorizationKey === authorizationKey
      ? (props.initialDeviation ?? undefined) as DeviationJsonView | undefined : undefined,
  })

  const [editForm] = Form.useForm()
  // 监听"偏差是否曾发生"勾选值，控制曾发生编号输入框的可用/显隐
  const hasOccurredBefore = Form.useWatch('has_occurred_before', editForm)

  useEffect(() => {
    if (props.initialLoadError) {
      message.error(props.initialLoadError)
      router.push('/quality/deviations/ledger')
    }
  }, [props.initialLoadError, message, router])

  useEffect(() => {
    if (error && !props.initialDeviation) {
      message.error(getErrorMessage(error, '加载失败'))
      router.push('/quality/deviations/ledger')
    }
  }, [error, message, router, props.initialDeviation])

  // 数据加载后回填表单（对齐桌面台账：可编辑区域直接展示可编辑内容）
  useEffect(() => {
    if (canQuery && deviation) {
      editForm.setFieldsValue({
        affected_items: deviation.affected_items,
        batch_number: deviation.batch_number,
        description: deviation.description,
        has_occurred_before: deviation.has_occurred_before,
        previous_occurrence_code: deviation.previous_occurrence_code,
        root_cause_analysis: deviation.root_cause_analysis,
        level: deviation.level,
        investigation_completed_at: deviation.investigation_completed_at ? dayjs(deviation.investigation_completed_at) : null,
        corrective_actions: deviation.corrective_actions,
        material_disposition: deviation.material_disposition,
        is_closed: deviation.status === 'closed',
      })
    } else {
      editForm.resetFields()
    }
  }, [canQuery, deviation, editForm])

  const handleSaveEdit = async () => {
    if (!canOperate || !deviation) return
    try {
      const values = await editForm.validateFields()
      // 组装更新数据：可编辑列对齐桌面台账
      await updateDeviation(deviation!.id, {
        description: values.description,
        affected_items: values.affected_items || null,
        batch_number: values.batch_number || null,
        has_occurred_before: values.has_occurred_before,
        // 曾发生编号为空串时提交 null，避免落库空字符串
        previous_occurrence_code: values.previous_occurrence_code || null,
        root_cause_analysis: values.root_cause_analysis,
        level: values.level,
        investigation_completed_at: values.investigation_completed_at
          ? values.investigation_completed_at.toISOString()
          : null,
        corrective_actions: values.corrective_actions,
        material_disposition: values.material_disposition,
        // 是否关闭：选择"是"时置为已关闭，否则恢复为草稿/进行中
        ...(workflowFieldsReadOnly ? {} : {
          status: values.is_closed === true ? 'closed' : values.is_closed === false && deviation!.status === 'closed' ? 'draft' : deviation!.status,
        }),
      })
      message.success('保存成功')
      queryClient.invalidateQueries({ queryKey: ['quality-deviation', 'detail', id] })
      queryClient.invalidateQueries({ queryKey: ['quality-deviation', 'list'] })
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '保存失败'))
    }
  }

  const handleDelete = () => {
    if (!canDelete || !deviation) return
    modal.confirm({
      title: '确认删除',
      content: '确定要删除此偏差吗？删除后记录将从台账隐藏，并保留操作审计。',
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        try {
          await deleteDeviation(deviation!.id)
          message.success('删除成功')
          router.push('/quality/deviations/ledger')
        } catch (error: unknown) {
          message.error(getErrorMessage(error, '删除失败'))
        }
      },
    })
  }

  if (!canQuery) {
    return <Alert type="info" showIcon title="尚未获得偏差台账查询权限，请联系系统管理员。" />
  }

  if (loading) {
    return <div>加载中...</div>
  }

  if (!deviation) {
    return <div>未找到偏差</div>
  }

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <Button icon={<ArrowLeftOutlined />} onClick={() => router.push('/quality/deviations/ledger')}>
            返回
          </Button>
          <h2 style={{ margin: 0 }}>{deviation.deviation_code}</h2>
        </Space>
        <Space>
          {canOperate && <Button type="primary" onClick={handleSaveEdit}>
            保存
          </Button>}
          {canDelete && <Button danger icon={<DeleteOutlined />} onClick={handleDelete}>
            删除
          </Button>}
        </Space>
      </div>

      <Card title={canOperate ? '偏差台账编辑' : '偏差台账详情（只读）'} style={{ marginBottom: 16 }}>
        <Form form={editForm} layout="vertical" disabled={!canOperate}>
          <Form.Item label="偏差编号">
            <Input value={deviation.deviation_code} disabled />
          </Form.Item>
          <Form.Item name="affected_items" label="产品名称">
            <Input placeholder="请输入产品名称" />
          </Form.Item>
          <Form.Item name="batch_number" label="批号">
            <Input placeholder="请输入批号" />
          </Form.Item>
          <Form.Item name="description" label="偏差简要描述">
            <TextArea rows={4} placeholder="请输入偏差简要描述" />
          </Form.Item>
          <Form.Item name="has_occurred_before" label="偏差是否曾发生" required>
            <Radio.Group
              onChange={(e) => {
                if (e.target.value === false) {
                  editForm.setFieldValue('previous_occurrence_code', null)
                }
              }}
            >
              <Radio value={true}>是</Radio>
              <Radio value={false}>否</Radio>
            </Radio.Group>
          </Form.Item>
          {hasOccurredBefore === true && (
            <Form.Item name="previous_occurrence_code" label="曾发生偏差编号（多个编号换行填写）">
              <TextArea rows={2} placeholder="请填写曾发生偏差编号，多个编号换行分隔" />
            </Form.Item>
          )}
          <Form.Item name="root_cause_analysis" label="根本原因">
            <TextArea rows={3} placeholder="请输入根本原因" />
          </Form.Item>
          <Form.Item name="level" label="偏差等级">
            <Select placeholder="请选择偏差等级" options={LEVEL_OPTIONS} allowClear />
          </Form.Item>
          <Form.Item name="investigation_completed_at" label="调查完成时间">
            <DatePicker
              showTime
              format="YYYY-MM-DD HH:mm"
              style={{ width: '100%' }}
              placeholder="请选择调查完成时间"
            />
          </Form.Item>
          <Form.Item name="corrective_actions" label="纠正预防措施">
            <TextArea rows={3} placeholder="请输入纠正预防措施" />
          </Form.Item>
          <Form.Item name="material_disposition" label="产品/物料处理结果">
            <TextArea rows={3} placeholder="请输入产品/物料处理结果" />
          </Form.Item>
          <Form.Item name="is_closed" label="是否关闭" extra={workflowFieldsReadOnly ? '关闭状态由业务流程维护，不能通过普通编辑修改。' : undefined}>
            <Select
              disabled={!canOperate || workflowFieldsReadOnly}
              placeholder="请选择是否关闭"
              options={[
                { label: '是', value: true },
                { label: '否', value: false },
              ]}
            />
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}
