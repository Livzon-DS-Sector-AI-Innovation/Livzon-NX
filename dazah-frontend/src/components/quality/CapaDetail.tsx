'use client'

import { useCallback, useEffect, useState } from 'react'
import { useRouter, useParams } from 'next/navigation'
import { App, Card, Descriptions, Tag, Button, Space, Modal, Form, Input, Select } from 'antd'
import { ArrowLeftOutlined, EditOutlined, DeleteOutlined, CheckCircleOutlined, SendOutlined, RedoOutlined, PlusOutlined, MinusCircleOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { fetchCapa } from '@/lib/api/quality'
import {
  updateCapa,
  deleteCapa,
  submitCapa,
  approveCapa,
  resubmitCapa,
  addExecutionTrack,
  deleteExecutionTrack,
  confirmExecution,
  submitEvaluation,
  completeCapaPart,
  confirmDeptHead,
} from '@/actions/quality'
import type { CapaDetail as CapaDetailType, CapaWorkflowStatus } from '@/types/quality'

const { TextArea } = Input

const STATUS_LABELS: Record<CapaWorkflowStatus, string> = {
  draft: '草稿',
  part_a: 'A部分',
  part_b: 'B部分',
  part_c: 'C部分',
  pending_dept_head_confirm: '待部门主管确认',
  pending_qa_review: '待QA审核',
  pending_q_head_approval: '待质量主管审批',
  executing: '执行中',
  pending_evaluation: '待效果评价',
  closed: '已关闭',
  returned: '已退回',
  submitted: '已提交',
  under_execution: '执行中',
  evaluation: '效果评价',
  cancelled: '已取消',
}

const STATUS_COLORS: Record<CapaWorkflowStatus, string> = {
  draft: 'default',
  part_a: 'blue',
  part_b: 'blue',
  part_c: 'blue',
  pending_dept_head_confirm: 'orange',
  pending_qa_review: 'orange',
  pending_q_head_approval: 'orange',
  executing: 'cyan',
  pending_evaluation: 'purple',
  closed: 'green',
  returned: 'red',
  submitted: 'blue',
  under_execution: 'cyan',
  evaluation: 'purple',
  cancelled: 'default',
}

const SOURCE_OPTIONS = [
  { label: '偏差', value: 'deviation' },
  { label: '客户投诉', value: 'complaint' },
  { label: '审计', value: 'audit' },
  { label: '自检', value: 'self_inspection' },
  { label: '其他', value: 'other' },
]

const CATEGORY_OPTIONS = [
  { label: 'A类', value: 'A' },
  { label: 'B类', value: 'B' },
  { label: 'C类', value: 'C' },
]

const REASON_CATEGORY_OPTIONS = [
  { label: '人为因素', value: 'human_error' },
  { label: '设备故障', value: 'equipment_failure' },
  { label: '物料问题', value: 'material_issue' },
  { label: '工艺问题', value: 'process_issue' },
  { label: '环境问题', value: 'environment_issue' },
  { label: '文件问题', value: 'document_issue' },
  { label: '其他', value: 'other' },
]

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

export function CapaDetail() {
  const router = useRouter()
  const params = useParams()
  const { message, modal } = App.useApp()

  const [capa, setCapa] = useState<CapaDetailType | null>(null)
  const [loading, setLoading] = useState(true)
  const [editMode, setEditMode] = useState(false)
  const [editForm] = Form.useForm()

  const [capaItemModalOpen, setCapaItemModalOpen] = useState(false)
  const [capaItemForm] = Form.useForm()

  const [reviewModalOpen, setReviewModalOpen] = useState(false)
  const [reviewForm] = Form.useForm()
  const [reviewStep, setReviewStep] = useState<string | null>(null)

  const [evaluationModalOpen, setEvaluationModalOpen] = useState(false)
  const [evaluationForm] = Form.useForm()

  const [executionModalOpen, setExecutionModalOpen] = useState(false)
  const [executionForm] = Form.useForm()

  const loadData = useCallback(async () => {
    try {
      const data = await fetchCapa(params.id as string)
      setCapa(data)
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '加载失败'))
      router.push('/quality/capas')
    } finally {
      setLoading(false)
    }
  }, [params.id, message, router])

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const data = await fetchCapa(params.id as string)
        if (!cancelled) setCapa(data)
      } catch (error: unknown) {
        if (!cancelled) {
          message.error(getErrorMessage(error, '加载失败'))
          router.push('/quality/capas')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [params.id, message, router])

  const handleEdit = () => {
    if (!capa) return
    editForm.setFieldsValue({
      title: capa.title,
      source: capa.source,
      source_code: capa.source_code,
      category: capa.category,
      root_cause_category: capa.root_cause_category,
      non_conformity_description: capa.non_conformity_description,
      root_cause_analysis: capa.root_cause_analysis,
      capa_content: capa.capa_content,
      expected_completion_date: capa.expected_completion_date ? dayjs(capa.expected_completion_date).format('YYYY-MM-DD') : null,
    })
    setEditMode(true)
  }

  const handleSaveEdit = async () => {
    try {
      const values = await editForm.validateFields()
      await updateCapa(capa!.id, {
        ...values,
        expected_completion_date: values.expected_completion_date ? new Date(values.expected_completion_date).toISOString() : undefined,
      })
      message.success('保存成功')
      setEditMode(false)
      loadData()
    } catch (error: unknown) {
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

  const handleAddCapaItem = async () => {
    try {
      const values = await capaItemForm.validateFields()
      const newItems = [...(capa!.capa_items || []), values]
      await updateCapa(capa!.id, { capa_items: newItems })
      message.success('CAPA项目已添加')
      setCapaItemModalOpen(false)
      capaItemForm.resetFields()
      loadData()
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '添加 CAPA 项目失败'))
    }
  }

  const handleRemoveCapaItem = async (index: number) => {
    const newItems = capa!.capa_items!.filter((_, i) => i !== index)
    await updateCapa(capa!.id, { capa_items: newItems })
    message.success('CAPA项目已删除')
    loadData()
  }

  const handleOpenReview = (step: string) => {
    setReviewStep(step)
    reviewForm.resetFields()
    setReviewModalOpen(true)
  }

  const handleSubmitReview = async () => {
    try {
      const values = await reviewForm.validateFields()
      await approveCapa(capa!.id, {
        step: reviewStep as 'qa_review' | 'q_head_approval',
        result: values.result,
        opinion: values.content,
      })
      message.success('审核意见已提交')
      setReviewModalOpen(false)
      reviewForm.resetFields()
      loadData()
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '提交审核意见失败'))
    }
  }

  const handleOpenEvaluation = () => {
    evaluationForm.resetFields()
    setEvaluationModalOpen(true)
  }

  const handleSubmitEvaluation = async () => {
    try {
      const values = await evaluationForm.validateFields()
      await submitEvaluation(capa!.id, {
        evaluation_target: values.evaluation_target,
        evaluation_result: values.evaluation_result,
        evaluation_confirmer: values.evaluation_confirmer_id,
        evaluation_confirm_date: new Date().toISOString(),
        closure_date: new Date().toISOString(),
      })
      message.success('效果评价已提交，CAPA已关闭')
      setEvaluationModalOpen(false)
      evaluationForm.resetFields()
      loadData()
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '提交效果评价失败'))
    }
  }

  const handleOpenExecution = () => {
    executionForm.resetFields()
    setExecutionModalOpen(true)
  }

  const handleSubmitExecution = async () => {
    try {
      const values = await executionForm.validateFields()
      await addExecutionTrack(capa!.id, {
        content: values.content,
        executor: values.executor || null,
        execution_date: values.execution_date || null,
        attachments: [],
      })
      message.success('执行记录已添加')
      setExecutionModalOpen(false)
      executionForm.resetFields()
      loadData()
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '添加执行记录失败'))
    }
  }

  const handleRemoveExecutionTrack = async (index: number) => {
    try {
      await deleteExecutionTrack(capa!.id, index)
      message.success('执行记录已删除')
      loadData()
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '删除执行记录失败'))
    }
  }

  const handleConfirmDeptHead = async (index: number, result: 'approved' | 'rejected') => {
    const confirmation = capa!.dept_head_confirmations![index]
    try {
      await confirmDeptHead(capa!.id, {
        department: confirmation.department,
        dept_head_user_id: confirmation.deptHeadUserId,
        result,
        opinion: '',
      })
      message.success('确认意见已提交')
      loadData()
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '提交确认意见失败'))
    }
  }

  const handleResubmit = async () => {
    modal.confirm({
      title: '确认重新提交',
      content: '确定要重新提交此CAPA吗？',
      okText: '确认',
      cancelText: '取消',
      onOk: async () => {
        try {
          await resubmitCapa(capa!.id)
          message.success('已重新提交')
          loadData()
        } catch (error: unknown) {
          message.error(getErrorMessage(error, '重新提交失败'))
        }
      },
    })
  }

  const handleSubmitCapa = async () => {
    modal.confirm({
      title: '确认提交审核',
      content: '确定要提交此CAPA进入审核流程吗？提交后不可编辑。',
      okText: '确认提交',
      cancelText: '取消',
      onOk: async () => {
        try {
          await submitCapa(capa!.id)
          message.success('已提交审核')
          loadData()
        } catch (error: unknown) {
          message.error(getErrorMessage(error, '提交失败'))
        }
      },
    })
  }

  const handleCompletePart = async (part: 'a' | 'b') => {
    try {
      await completeCapaPart(capa!.id, part)
      message.success(`Part ${part.toUpperCase()} 已完成`)
      loadData()
    } catch (error: unknown) {
      message.error(getErrorMessage(error, `Part ${part.toUpperCase()} 完成失败`))
    }
  }

  const handleConfirmExecution = async () => {
    modal.confirm({
      title: '确认执行完成',
      content: '确定要确认所有执行记录已完成吗？',
      okText: '确认',
      cancelText: '取消',
      onOk: async () => {
        try {
          await confirmExecution(capa!.id)
          message.success('执行已确认')
          loadData()
        } catch (error: unknown) {
          message.error(getErrorMessage(error, '确认失败'))
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

  const canEdit = capa.status === 'draft' || capa.status === 'returned' || capa.status.startsWith('part_')
  const canDelete = capa.status === 'draft'
  const canAddCapaItem = capa.status.startsWith('part_') || capa.status === 'draft'

  return (
      <div>
        <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Space>
            <Button icon={<ArrowLeftOutlined />} onClick={() => router.push('/quality/capas')}>
              返回
            </Button>
            <h2 style={{ margin: 0 }}>{capa.capa_code}</h2>
            <Tag color={STATUS_COLORS[capa.status]}>
              {STATUS_LABELS[capa.status]}
              {capa.status === 'returned' && capa.returned_step && ` (${capa.returned_step})`}
            </Tag>
          </Space>
          <Space>
            {canEdit && (
              <>
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
              </>
            )}
            {canDelete && (
              <Button danger icon={<DeleteOutlined />} onClick={handleDelete}>
                删除
              </Button>
            )}
            {capa.status === 'draft' && (
              <Button type="primary" icon={<SendOutlined />} onClick={handleSubmitCapa}>
                提交审核
              </Button>
            )}
            {capa.status === 'part_a' && (
              <Button type="primary" icon={<CheckCircleOutlined />} onClick={() => handleCompletePart('a')}>
                完成 Part A
              </Button>
            )}
            {capa.status === 'part_b' && (
              <Button type="primary" icon={<CheckCircleOutlined />} onClick={() => handleCompletePart('b')}>
                完成 Part B
              </Button>
            )}
            {canAddCapaItem && (
              <Button icon={<PlusOutlined />} onClick={() => setCapaItemModalOpen(true)}>
                添加CAPA项目
              </Button>
            )}
            {capa.status === 'pending_dept_head_confirm' && capa.dept_head_confirmations && (
              <span style={{ color: '#999' }}>等待部门主管确认</span>
            )}
            {capa.status === 'pending_qa_review' && (
              <Button type="primary" icon={<CheckCircleOutlined />} onClick={() => handleOpenReview('qa_review')}>
                提交审核意见
              </Button>
            )}
            {capa.status === 'pending_q_head_approval' && (
              <Button type="primary" icon={<CheckCircleOutlined />} onClick={() => handleOpenReview('q_head_approval')}>
                提交审批意见
              </Button>
            )}
            {capa.status === 'executing' && (
              <>
                <Button icon={<PlusOutlined />} onClick={handleOpenExecution}>
                  添加执行记录
                </Button>
                <Button type="primary" onClick={handleOpenEvaluation}>
                  提交效果评价
                </Button>
                <Button type="primary" icon={<CheckCircleOutlined />} onClick={handleConfirmExecution}>
                  确认执行完成
                </Button>
              </>
            )}
            {capa.status === 'pending_evaluation' && (
              <Button type="primary" onClick={handleOpenEvaluation}>
                提交效果评价
              </Button>
            )}
            {capa.status === 'returned' && (
              <Button icon={<RedoOutlined />} onClick={handleResubmit}>
                重新提交
              </Button>
            )}
          </Space>
        </div>

        {!editMode ? (
          <Card title="基本信息" style={{ marginBottom: 16 }}>
            <Descriptions column={2}>
              <Descriptions.Item label="标题">{capa.title || '-'}</Descriptions.Item>
              <Descriptions.Item label="来源">
                {capa.source ? SOURCE_OPTIONS.find(o => o.value === capa.source)?.label || capa.source : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="来源编号">{capa.source_code || '-'}</Descriptions.Item>
              <Descriptions.Item label="类别">
                {capa.category ? CATEGORY_OPTIONS.find(o => o.value === capa.category)?.label || capa.category : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="原因类别">
                {capa.root_cause_category ? REASON_CATEGORY_OPTIONS.find(o => o.value === capa.root_cause_category)?.label || capa.root_cause_category : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="预期完成日期">
                {capa.expected_completion_date ? dayjs(capa.expected_completion_date).format('YYYY-MM-DD') : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="不符合事项描述" span={2}>
                {capa.non_conformity_description || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="根本原因分析" span={2}>
                {capa.root_cause_analysis || '-'}
              </Descriptions.Item>
              <Descriptions.Item label="CAPA内容" span={2}>
                {capa.capa_content || '-'}
              </Descriptions.Item>
              {capa.final_code && (
                <Descriptions.Item label="最终编号">{capa.final_code}</Descriptions.Item>
              )}
              {capa.closure_date && (
                <Descriptions.Item label="关闭日期">
                  {dayjs(capa.closure_date).format('YYYY-MM-DD')}
                </Descriptions.Item>
              )}
            </Descriptions>
          </Card>
        ) : (
          <Card title="编辑基本信息" style={{ marginBottom: 16 }}>
            <Form form={editForm} layout="vertical">
              <Form.Item name="title" label="标题" rules={[{ required: true, message: '请输入标题' }]}>
                <Input />
              </Form.Item>
              <Form.Item name="source" label="来源">
                <Select options={SOURCE_OPTIONS} allowClear />
              </Form.Item>
              <Form.Item name="source_code" label="来源编号">
                <Input />
              </Form.Item>
              <Form.Item name="category" label="类别">
                <Select options={CATEGORY_OPTIONS} allowClear />
              </Form.Item>
              <Form.Item name="root_cause_category" label="原因类别">
                <Select options={REASON_CATEGORY_OPTIONS} allowClear />
              </Form.Item>
              <Form.Item name="expected_completion_date" label="预期完成日期">
                <Input type="date" />
              </Form.Item>
              <Form.Item name="non_conformity_description" label="不符合事项描述">
                <TextArea rows={3} />
              </Form.Item>
              <Form.Item name="root_cause_analysis" label="根本原因分析">
                <TextArea rows={4} />
              </Form.Item>
              <Form.Item name="capa_content" label="CAPA内容">
                <TextArea rows={4} />
              </Form.Item>
            </Form>
          </Card>
        )}

        {capa.capa_items && capa.capa_items.length > 0 && (
          <Card title="CAPA项目" style={{ marginBottom: 16 }}>
            <div style={{ display: 'grid', gap: 16 }}>
              {capa.capa_items.map((item, index) => (
                <div
                  key={`${item.content}-${index}`}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'flex-start',
                    gap: 16,
                    paddingBottom: index < capa.capa_items!.length - 1 ? 16 : 0,
                    borderBottom: index < capa.capa_items!.length - 1 ? '1px solid #f0f0f0' : 'none',
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 500, marginBottom: 4 }}>{item.content}</div>
                    <div style={{ color: '#787671' }}>
                      {`执行人: ${item.responsible_person || '-'} | 预期完成: ${
                        item.deadline ? dayjs(item.deadline).format('YYYY-MM-DD') : '-'
                      }`}
                    </div>
                  </div>
                  {canAddCapaItem ? (
                    <Button
                      type="link"
                      danger
                      icon={<MinusCircleOutlined />}
                      onClick={() => handleRemoveCapaItem(index)}
                    />
                  ) : null}
                </div>
              ))}
            </div>
          </Card>
        )}

        {capa.dept_head_confirmations && capa.dept_head_confirmations.length > 0 && (
          <Card title="部门主管确认" style={{ marginBottom: 16 }}>
            <div style={{ display: 'grid', gap: 16 }}>
              {capa.dept_head_confirmations.map((confirmation, index) => (
                <div
                  key={`${confirmation.department}-${index}`}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'flex-start',
                    gap: 16,
                    paddingBottom: index < capa.dept_head_confirmations!.length - 1 ? 16 : 0,
                    borderBottom:
                      index < capa.dept_head_confirmations!.length - 1 ? '1px solid #f0f0f0' : 'none',
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 500, marginBottom: 8 }}>{confirmation.department}</div>
                    <div>部门主管: {confirmation.deptHeadUserId}</div>
                    {confirmation.result ? (
                      <div style={{ marginTop: 8 }}>
                        <Tag color={confirmation.result === 'approved' ? 'green' : 'red'}>
                          {confirmation.result === 'approved' ? '已确认' : '已退回'}
                        </Tag>
                        {confirmation.confirmTime
                          ? dayjs(confirmation.confirmTime).format('YYYY-MM-DD HH:mm')
                          : null}
                      </div>
                    ) : null}
                    {confirmation.opinion ? <div style={{ marginTop: 8 }}>意见: {confirmation.opinion}</div> : null}
                  </div>
                  {capa.status === 'pending_dept_head_confirm' && !confirmation.result ? (
                    <Space>
                      <Button type="primary" size="small" onClick={() => handleConfirmDeptHead(index, 'approved')}>
                        确认
                      </Button>
                      <Button danger size="small" onClick={() => handleConfirmDeptHead(index, 'rejected')}>
                        退回
                      </Button>
                    </Space>
                  ) : null}
                </div>
              ))}
            </div>
          </Card>
        )}

        {capa.qa_review_opinion && (
          <Card title="QA审核意见" style={{ marginBottom: 16 }}>
            <Descriptions column={1}>
              <Descriptions.Item label="审核意见">{capa.qa_review_opinion}</Descriptions.Item>
              <Descriptions.Item label="审核时间">
                {capa.qa_review_time ? dayjs(capa.qa_review_time).format('YYYY-MM-DD HH:mm') : '-'}
              </Descriptions.Item>
            </Descriptions>
          </Card>
        )}

        {capa.q_head_approval_opinion && (
          <Card title="质量主管审批意见" style={{ marginBottom: 16 }}>
            <Descriptions column={1}>
              <Descriptions.Item label="审批意见">{capa.q_head_approval_opinion}</Descriptions.Item>
              <Descriptions.Item label="审批时间">
                {capa.q_head_approval_time ? dayjs(capa.q_head_approval_time).format('YYYY-MM-DD HH:mm') : '-'}
              </Descriptions.Item>
            </Descriptions>
          </Card>
        )}

        {capa.execution_tracks && capa.execution_tracks.length > 0 && (
          <Card title="执行记录" style={{ marginBottom: 16 }}>
            <div style={{ display: 'grid', gap: 16 }}>
              {capa.execution_tracks.map((track, index) => (
                <div
                  key={`${track.content}-${index}`}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'flex-start',
                    gap: 16,
                    paddingBottom: index < capa.execution_tracks!.length - 1 ? 16 : 0,
                    borderBottom: index < capa.execution_tracks!.length - 1 ? '1px solid #f0f0f0' : 'none',
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 500, marginBottom: 8 }}>{`记录 ${index + 1}`}</div>
                    <div>执行内容: {track.content}</div>
                    {track.executor ? <div>执行人: {track.executor}</div> : null}
                    {track.execution_date ? (
                      <div>执行日期: {dayjs(track.execution_date).format('YYYY-MM-DD')}</div>
                    ) : null}
                  </div>
                  {capa.status === 'executing' ? (
                    <Button
                      type="link"
                      danger
                      icon={<MinusCircleOutlined />}
                      onClick={() => handleRemoveExecutionTrack(index)}
                    />
                  ) : null}
                </div>
              ))}
            </div>
          </Card>
        )}

        {capa.evaluation_result && (
          <Card title="效果评价" style={{ marginBottom: 16 }}>
            <Descriptions column={1}>
              <Descriptions.Item label="评价目标">{capa.evaluation_target || '-'}</Descriptions.Item>
              <Descriptions.Item label="评价结果">{capa.evaluation_result}</Descriptions.Item>
              <Descriptions.Item label="评价截止日期">
                {capa.evaluation_deadline ? dayjs(capa.evaluation_deadline).format('YYYY-MM-DD') : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="评价确认人">{capa.evaluation_confirmer_id || '-'}</Descriptions.Item>
              <Descriptions.Item label="评价确认日期">
                {capa.evaluation_confirm_date ? dayjs(capa.evaluation_confirm_date).format('YYYY-MM-DD HH:mm') : '-'}
              </Descriptions.Item>
            </Descriptions>
          </Card>
        )}

        <Modal
          title="添加CAPA项目"
          open={capaItemModalOpen}
          onOk={handleAddCapaItem}
          onCancel={() => setCapaItemModalOpen(false)}
          width={600}
        >
          <Form form={capaItemForm} layout="vertical">
            <Form.Item name="content" label="项目内容" rules={[{ required: true, message: '请输入项目内容' }]}>
              <TextArea rows={3} />
            </Form.Item>
            <Form.Item name="executors" label="执行人">
              <Input />
            </Form.Item>
            <Form.Item name="expectedCompletionDate" label="预期完成日期">
              <Input type="date" />
            </Form.Item>
          </Form>
        </Modal>

        <Modal
          title={`提交审核意见 - ${reviewStep === 'qa_review' ? 'QA审核' : '质量主管审批'}`}
          open={reviewModalOpen}
          onOk={handleSubmitReview}
          onCancel={() => setReviewModalOpen(false)}
          width={600}
        >
          <Form form={reviewForm} layout="vertical">
            <Form.Item name="result" label="审核结果" rules={[{ required: true, message: '请选择审核结果' }]}>
              <Select>
                <Select.Option value="approved">通过</Select.Option>
                <Select.Option value="rejected">退回</Select.Option>
              </Select>
            </Form.Item>
            <Form.Item name="content" label="审核意见" rules={[{ required: true, message: '请输入审核意见' }]}>
              <TextArea rows={4} />
            </Form.Item>
          </Form>
        </Modal>

        <Modal
          title="提交效果评价"
          open={evaluationModalOpen}
          onOk={handleSubmitEvaluation}
          onCancel={() => setEvaluationModalOpen(false)}
          width={600}
        >
          <Form form={evaluationForm} layout="vertical">
            <Form.Item name="evaluation_target" label="评价目标">
              <TextArea rows={2} />
            </Form.Item>
            <Form.Item name="evaluation_result" label="评价结果" rules={[{ required: true, message: '请输入评价结果' }]}>
              <TextArea rows={4} />
            </Form.Item>
            <Form.Item name="evaluation_deadline" label="评价截止日期">
              <Input type="date" />
            </Form.Item>
            <Form.Item name="evaluation_confirmer_id" label="评价确认人">
              <Input />
            </Form.Item>
          </Form>
        </Modal>

        <Modal
          title="添加执行记录"
          open={executionModalOpen}
          onOk={handleSubmitExecution}
          onCancel={() => setExecutionModalOpen(false)}
          width={600}
        >
          <Form form={executionForm} layout="vertical">
            <Form.Item name="content" label="执行内容" rules={[{ required: true, message: "请输入执行内容" }]}>
              <Input.TextArea rows={3} />
            </Form.Item>
            <Form.Item name="executor" label="执行人">
              <Input />
            </Form.Item>
            <Form.Item name="execution_date" label="执行日期">
              <Input type="date" />
            </Form.Item>
          </Form>
        </Modal>
      </div>
  )
}
