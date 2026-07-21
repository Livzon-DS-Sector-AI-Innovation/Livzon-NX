'use client'

"use client"

'use client'

import { useEffect, useState } from 'react'
import { useRouter, useParams } from 'next/navigation'
import {
  Card,
  Descriptions,
  Tag,
  Button,
  Space,
  Typography,
  App,
  Spin,
  Divider,
  Steps,
  Modal,
  Input,
  Row,
  Col,
  Statistic,
  Collapse,
} from 'antd'
import {
  ArrowLeftOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ThunderboltOutlined,
  SafetyOutlined,
  ExperimentOutlined,
  FileTextOutlined,
  RobotOutlined,
  EditOutlined,
} from '@ant-design/icons'
import {
  getHazardIdentification,
  runHazardScript,
  reviewHazardScript,
  updateHazardIdentification,
} from '@/actions/safety'
import type { HazardIdentification } from '@/types/safety'
import {
  AI_NODE_PROGRESS_OPTIONS,
  OVERALL_STATUS_OPTIONS_HI,
  REVIEW_STATUS_OPTIONS,
  RISK_LEVEL_OPTIONS,
  RECOMMENDATION_PRIORITY_OPTIONS,
} from '@/types/safety'
import dayjs from 'dayjs'
import { getWorkflowStepList } from '@/lib/workflow-templates'

const { Title, Text } = Typography

// ── 步骤图标映射（React 组件，不能放 .ts 文件） ──
const STEP_ICONS: Record<number, React.ReactNode> = {
  1: <FileTextOutlined />,
  2: <RobotOutlined />,
  3: <ExperimentOutlined />,
  4: <SafetyOutlined />,
  5: <ExperimentOutlined />,
  6: <ThunderboltOutlined />,
  7: <SafetyOutlined />,
}

// ── 工作流步骤配置（从共享模板派生） ──
const WORKFLOW_STEPS = getWorkflowStepList('hazard-identification').map((s) => ({
  ...s,
  icon: STEP_ICONS[s.num] || <RobotOutlined />,
}))

export default function HazardIdentificationDetailPage() {
  const router = useRouter()
  const params = useParams()
  const id = params.id as string

  const [record, setRecord] = useState<HazardIdentification | null>(null)
  const [loading, setLoading] = useState(true)
  const [runningScript, setRunningScript] = useState<number | null>(null)
  const [selectedStep, setSelectedStep] = useState(1)
  const [editModalVisible, setEditModalVisible] = useState(false)
  const [editingScript, setEditingScript] = useState<number>(0)
  const [editForm, setEditForm] = useState<Record<string, unknown>>({})
  const { message } = App.useApp()

  const loadRecord = async () => {
    try {
      const response = await getHazardIdentification(id)
      if (response.code === 200) {
        setRecord(response.data)
        // 自动选中当前步骤
        const data = response.data as HazardIdentification
        const cur = getCurrentStepNum(data.ai_node_progress)
        setSelectedStep(cur)
      } else {
        message.error('加载失败')
        router.push('/safety/hazard-identification')
      }
    } catch {
      message.error('加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (id) loadRecord()
  }, [id])

  const getCurrentStepNum = (progress: string): number => {
    if (progress === 'completed') return 7
    const match = progress.match(/script(\d)/)
    return match ? parseInt(match[1]) : 1
  }

  const handleRunScript = async (scriptNum: number) => {
    setRunningScript(scriptNum)
    try {
      const response = await runHazardScript(id, scriptNum)
      if (response.code === 200) {
        const data = response.data as HazardIdentification
        if (data.ai_error_message) {
          message.warning(`工作流${scriptNum}执行异常：${data.ai_error_message}`)
        } else {
          message.success(`工作流${scriptNum}「${WORKFLOW_STEPS[scriptNum - 1].title}」执行完成`)
        }
        setRecord(data)
        // 自动跳到下一步
        const nextStep = getCurrentStepNum(data.ai_node_progress)
        setSelectedStep(nextStep)
      } else {
        message.error(response.message || '工作流执行失败')
      }
    } catch {
      message.error('工作流执行失败')
    } finally {
      setRunningScript(null)
    }
  }

  const handleReview = async (scriptNum: number, action: 'approved' | 'rejected') => {
    try {
      const response = await reviewHazardScript(id, scriptNum, action)
      if (response.code === 200) {
        message.success(action === 'approved' ? '审核通过' : '已驳回')
        setRecord(response.data as HazardIdentification)
      } else {
        message.error(response.message || '审核操作失败')
      }
    } catch {
      message.error('审核操作失败')
    }
  }

  const handleEditConfirm = async () => {
    try {
      const response = await updateHazardIdentification(id, editForm as Record<string, unknown>)
      if (response.code === 200) {
        message.success('更新成功')
        setRecord(response.data as HazardIdentification)
        setEditModalVisible(false)
      } else {
        message.error(response.message || '更新失败')
      }
    } catch {
      message.error('更新失败')
    }
  }

  const openEditModal = (scriptNum: number, fields: Record<string, unknown>) => {
    setEditingScript(scriptNum)
    setEditForm(fields)
    setEditModalVisible(true)
  }

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 400 }}>
        <Spin size="large" />
      </div>
    )
  }

  if (!record) return null

  const currentStepNum = getCurrentStepNum(record.ai_node_progress)
  const currentStep = WORKFLOW_STEPS[selectedStep - 1]
  const currentOutputFields = getScriptOutputFields(selectedStep, record)
  const hasOutput = Object.values(currentOutputFields).some(
    (v) => v !== null && v !== undefined && v !== ''
  )
  const reviewStatus = (record as unknown as Record<string, unknown>)[`script${selectedStep}_review_status`] as string
  const isCurrent = record.ai_node_progress === `pending_script${selectedStep}`
  const isPast = selectedStep <= currentStepNum
  const canRun = isCurrent || reviewStatus === 'rejected'

  return (
    <div style={{ padding: 24, maxWidth: 1400, margin: '0 auto' }}>
      {/* 返回 */}
      <Button
        type="text"
        icon={<ArrowLeftOutlined />}
        onClick={() => router.push('/safety/hazard-identification')}
        style={{ marginBottom: 16 }}
      >
        返回列表
      </Button>

      {/* 标题 & 状态 */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        marginBottom: 24,
      }}>
        <div>
          <h1 style={{ fontSize: 18, fontWeight: 600, color: '#1a1a1a', margin: 0 }}>
            危险源辨识详情
          </h1>
          <Text style={{ color: '#5d5b54' }}>编号：{record.hazard_id_no}</Text>
        </div>
        <Space>
          {getStatusTag(record.overall_status)}
          {getProgressTag(record.ai_node_progress)}
        </Space>
      </div>

      {/* 基础信息 (折叠) */}
      <Collapse
        items={[{
          key: 'basic',
          label: <Space><FileTextOutlined /><span>基础信息</span></Space>,
          children: (
            <Descriptions column={3} size="small" bordered>
              <Descriptions.Item label="危险源编号">{record.hazard_id_no}</Descriptions.Item>
              <Descriptions.Item label="部门">{record.department}</Descriptions.Item>
              <Descriptions.Item label="岗位">{record.position}</Descriptions.Item>
              <Descriptions.Item label="生产步骤" span={3}>
                {record.production_step}
              </Descriptions.Item>
              {record.attachment_original_name && (
                <Descriptions.Item label="附件" span={3}>
                  {record.attachment_original_name}
                </Descriptions.Item>
              )}
              <Descriptions.Item label="创建时间">
                {dayjs(record.created_at).format('YYYY-MM-DD HH:mm')}
              </Descriptions.Item>
              <Descriptions.Item label="更新时间">
                {dayjs(record.updated_at).format('YYYY-MM-DD HH:mm')}
              </Descriptions.Item>
              {record.notes && (
                <Descriptions.Item label="备注" span={3}>{record.notes}</Descriptions.Item>
              )}
            </Descriptions>
          ),
        }]}
        style={{ marginBottom: 24, borderRadius: 12 }}
      />

      {/* 流程进度 Steps */}
      <Card style={{ marginBottom: 24, borderRadius: 12, border: '1px solid #e5e3df' }}>
        <Steps
          current={currentStepNum - 1}
          status={record.overall_status === 'completed' ? 'finish' : 'process'}
          size="small"
          onChange={(step) => setSelectedStep(step + 1)}
          items={WORKFLOW_STEPS.map((s, i) => {
            const rs = (record as unknown as Record<string, unknown>)[`script${s.num}_review_status`] as string
            let status: 'wait' | 'process' | 'finish' | 'error' = 'wait'
            if (rs === 'approved' || (i < currentStepNum - 1)) status = 'finish'
            else if (i === currentStepNum - 1) status = 'process'
            if (rs === 'rejected') status = 'error'
            return {
              title: s.title,
              status: record.overall_status === 'completed' ? 'finish' : status,
            }
          })}
        />
      </Card>

      {/* 左右分栏 */}
      <div style={{ display: 'flex', gap: 16 }}>
        {/* 左侧：步骤选择 */}
        <div style={{ width: 420, flexShrink: 0, display: 'flex' }}>
          <Card
            size="small"
            title={
              <Space>
                {currentStep.icon}
                <span>步骤{selectedStep}：{currentStep.title}</span>
              </Space>
            }
            style={{ borderRadius: 12, border: '1px solid #e5e3df', flex: 1 }}
            styles={{ body: { padding: 16 } }}
          >
            <Text type="secondary" style={{ display: 'block', marginBottom: 16, fontSize: 13 }}>
              {currentStep.desc}
            </Text>

            {WORKFLOW_STEPS.map((step) => (
              <div
                key={step.num}
                onClick={() => setSelectedStep(step.num)}
                style={{
                  cursor: 'pointer',
                  padding: '8px 12px',
                  borderRadius: 8,
                  marginBottom: 4,
                  background: selectedStep === step.num ? '#f0edff' : 'transparent',
                  border: selectedStep === step.num ? '1px solid #5645d4' : '1px solid transparent',
                  transition: 'all 0.2s',
                }}
              >
                <Space>
                  {step.icon}
                  <Text
                    style={{
                      fontSize: 13,
                      fontWeight: selectedStep === step.num ? 600 : 400,
                      color: selectedStep === step.num ? '#5645d4' : '#37352f',
                    }}
                  >
                    {step.num}. {step.title}
                  </Text>
                </Space>
              </div>
            ))}
          </Card>
        </div>

        {/* 右侧：输出结果 + 操作 */}
        <div style={{ flex: 1, minWidth: 0, display: 'flex' }}>
          {/* 输出结果 */}
          <Card
            size="small"
            title={`步骤${selectedStep}：${currentStep.title} — 输出结果`}
            extra={
              <Space>
                {canRun && (
                  <Button
                    type="primary"
                    size="small"
                    icon={<ThunderboltOutlined />}
                    loading={runningScript === selectedStep}
                    onClick={() => handleRunScript(selectedStep)}
                  >
                    执行AI
                  </Button>
                )}
                {hasOutput && (
                  <Button
                    size="small"
                    icon={<EditOutlined />}
                    onClick={() => openEditModal(selectedStep, currentOutputFields)}
                  >
                    编辑
                  </Button>
                )}
                {isPast && reviewStatus === 'pending' && hasOutput && (
                  <>
                    <Button
                      size="small"
                      type="primary"
                      icon={<CheckCircleOutlined />}
                      onClick={() => handleReview(selectedStep, 'approved')}
                    >
                      审核通过
                    </Button>
                    <Button
                      size="small"
                      danger
                      icon={<CloseCircleOutlined />}
                      onClick={() => handleReview(selectedStep, 'rejected')}
                    >
                      驳回
                    </Button>
                  </>
                )}
                {reviewStatus === 'approved' && (
                  <Tag color="success" icon={<CheckCircleOutlined />}>已审核</Tag>
                )}
                {reviewStatus === 'rejected' && (
                  <Tag color="error" icon={<CloseCircleOutlined />}>已驳回</Tag>
                )}
              </Space>
            }
            style={{ borderRadius: 12, border: '1px solid #e5e3df', flex: 1 }}
          >
            {reviewStatus === 'rejected' && record.ai_error_message && (
              <div style={{
                marginBottom: 12, padding: '8px 12px', background: '#fff2f0',
                border: '1px solid #ffccc7', borderRadius: 8, fontSize: 13, color: '#e03131',
              }}>
                ⚠️ {record.ai_error_message}
              </div>
            )}
            {hasOutput ? (
              <Descriptions size="small" column={1} bordered>
                {Object.entries(currentOutputFields)
                  .filter(([, v]) => v !== null && v !== undefined && v !== '')
                  .map(([key, val]) => (
                    <Descriptions.Item key={key} label={getFieldLabel(selectedStep, key)}>
                      {renderFieldValue(selectedStep, key, val)}
                    </Descriptions.Item>
                  ))}
              </Descriptions>
            ) : (
              <Text type="secondary" italic>
                {canRun
                  ? '点击「执行AI」按钮运行工作流'
                  : selectedStep <= currentStepNum
                    ? '等待前序工作流审核通过后自动执行'
                    : '等待前序工作流完成'}
              </Text>
            )}
          </Card>
        </div>
      </div>

      {/* 风险等级汇总 */}
      {record.inherent_risk_level && (
        <>
          <Divider />
          <Title level={5} style={{ marginBottom: 16 }}>风险等级汇总</Title>
          <Row gutter={16}>
            {renderRiskCard('固有风险', record.inherent_risk_level, record.inherent_risk_label, record.d_inherent)}
            {renderRiskCard('残余风险', record.residual_risk_level, record.residual_risk_label, record.d_residual)}
            {renderRiskCard('措施后风险', record.post_risk_level, record.post_risk_label, record.d_post)}
          </Row>
          {record.control_level && (
            <Card size="small" style={{ marginTop: 16, borderRadius: 12 }}>
              <Space>
                <SafetyOutlined style={{ color: '#5645d4' }} />
                <Text strong>管控层级：{record.control_level}</Text>
                <Text type="secondary">责任人：{record.responsible_person || '-'}</Text>
              </Space>
            </Card>
          )}
        </>
      )}

      {/* 编辑Modal */}
      <Modal
        title={`编辑步骤${editingScript}字段`}
        open={editModalVisible}
        onOk={handleEditConfirm}
        onCancel={() => setEditModalVisible(false)}
        okText="确认"
        cancelText="取消"
        width={600}
        destroyOnHidden
      >
        {Object.entries(editForm).map(([key, val]) => (
          <div key={key} style={{ marginBottom: 12 }}>
            <Text strong style={{ display: 'block', marginBottom: 4, fontSize: 13 }}>
              {getFieldLabel(editingScript, key)}
            </Text>
            <Input.TextArea
              rows={2}
              value={val as string}
              onChange={(e) => setEditForm((prev) => ({ ...prev, [key]: e.target.value }))}
            />
          </div>
        ))}
      </Modal>
    </div>
  )
}

// ==================== Helper Functions ====================

function getStatusTag(value: string) {
  const opt = OVERALL_STATUS_OPTIONS_HI.find((o) => o.value === value)
  return <Tag color={opt?.color}>{opt?.label || value}</Tag>
}

function getProgressTag(value: string) {
  const opt = AI_NODE_PROGRESS_OPTIONS.find((o) => o.value === value)
  return <Tag color={opt?.color}>{opt?.label || value}</Tag>
}

function getFieldLabel(scriptNum: number, field: string): string {
  const labels: Record<string, Record<string, string>> = {
    1: {
      specific_activity: '具体作业活动',
      equipment_facilities: '设备设施',
      raw_auxiliary_materials: '原辅料',
    },
    2: {
      hazard_type: '危险类型',
      possible_accident: '可能导致事故',
      unsafe_behavior: '不规范作业行为表现',
    },
    3: {
      l_inherent: '可能性L（固有）', e_inherent: '暴露频率E（固有）',
      c_inherent: '严重性C（固有）', d_inherent: '风险值D（固有）',
      inherent_risk_level: '固有风险等级', inherent_risk_label: '固有风险等级名称',
    },
    4: {
      existing_engineering_controls: '现有工程控制措施',
      existing_management_controls: '现有管理控制措施',
      existing_ppe: '现有个人防护措施',
      existing_emergency_measures: '现有应急措施',
    },
    5: {
      l_residual: '可能性L（残余）', e_residual: '暴露频率E（残余）',
      c_residual: '严重性C（残余）', d_residual: '风险值D（残余）',
      residual_risk_level: '残余风险等级', residual_risk_label: '残余风险等级名称',
    },
    6: {
      needs_recommendation: '是否需提出建议措施',
      recommendation_type: '建议措施类型',
      recommendation_content: '建议措施内容',
      recommendation_priority: '建议措施优先级',
    },
    7: {
      l_post: '可能性L（措施后）', e_post: '暴露频率E（措施后）',
      c_post: '严重性C（措施后）', d_post: '风险值D（措施后）',
      post_risk_level: '措施后风险等级', post_risk_label: '措施后风险等级名称',
    },
  }
  return labels[scriptNum]?.[field] || field
}

function renderFieldValue(scriptNum: number, key: string, val: unknown) {
  if (['inherent_risk_level', 'residual_risk_level', 'post_risk_level'].includes(key)) {
    const opt = RISK_LEVEL_OPTIONS.find((o) => o.value === val)
    return <Tag color={opt?.color}>{opt?.label || String(val)}</Tag>
  }
  if (key === 'recommendation_priority') {
    const opt = RECOMMENDATION_PRIORITY_OPTIONS.find((o) => o.value === val)
    return <Tag color={opt?.color}>{opt?.label || String(val)}</Tag>
  }
  return String(val ?? '-')
}

function getScriptOutputFields(scriptNum: number, record: HazardIdentification): Record<string, unknown> {
  const step = WORKFLOW_STEPS.find((s) => s.num === scriptNum)
  const fields = step?.expected_keys || []
  const result: Record<string, unknown> = {}
  for (const f of fields) {
    result[f] = (record as unknown as Record<string, unknown>)[f]
  }
  return result
}

function renderRiskCard(label: string, levelKey?: string, levelLabel?: string, dValue?: number) {
  if (!levelKey) return null
  const opt = RISK_LEVEL_OPTIONS.find((o) => o.value === levelKey)
  return (
    <Col span={8}>
      <Card size="small" style={{ textAlign: 'center', borderRadius: 12 }}>
        <Statistic
          title={label}
          value={dValue ?? '-'}
          suffix={dValue ? 'D值' : ''}
          styles={{ content: { color: opt?.color || '#000' } }}
        />
        <Tag color={opt?.color} style={{ marginTop: 8 }}>{levelLabel || levelKey}</Tag>
      </Card>
    </Col>
  )
}
