'use client'

import { useState } from 'react'
import { Card, Input, Button, Space, Tag, Table, Form, DatePicker, Select, Alert, App, Collapse, Descriptions, Upload } from 'antd'
import { UploadOutlined, RobotOutlined, WarningOutlined, CheckCircleOutlined, PlusOutlined, FileTextOutlined } from '@ant-design/icons'
import type { ExperimentRecord, ExperimentPlan } from '@/types/rd'
import dayjs from 'dayjs'

interface ModuleTrialProps {
  routeId: string
  selectedRouteName: string
  experimentPlan?: ExperimentPlan
  initialExperiments?: ExperimentRecord[]
  onComplete: (experiments: ExperimentRecord[]) => void
}

const statusMap: Record<string, { color: string; label: string }> = {
  planned: { color: 'default', label: '计划中' },
  in_progress: { color: 'processing', label: '进行中' },
  completed: { color: 'success', label: '已完成' },
  failed: { color: 'error', label: '失败' },
}

export function ModuleTrial({ routeId, selectedRouteName, experimentPlan, initialExperiments = [], onComplete }: ModuleTrialProps) {
  const { message } = App.useApp()
  const [experiments, setExperiments] = useState<ExperimentRecord[]>(initialExperiments)
  const [experimentFiles, setExperimentFiles] = useState<any[]>([])
  const [showForm, setShowForm] = useState(false)
  const [form] = Form.useForm()

  const handleAddExperiment = async () => {
    try {
      const values = await form.validateFields()
      const newExp: ExperimentRecord = {
        id: `exp-${Date.now()}`,
        route_id: routeId,
        experiment_no: `EXP-${new Date().getFullYear()}-${String(experiments.length + 1).padStart(3, '0')}`,
        title: values.title,
        description: values.description || '',
        date: values.date.format('YYYY-MM-DD'),
        operator: values.operator,
        status: values.status,
        reaction_temp: values.reaction_temp,
        reaction_time: values.reaction_time,
        yield: values.yield ? Number(values.yield) : undefined,
        purity: values.purity ? Number(values.purity) : undefined,
        impurities: values.impurities,
        result_summary: values.result_summary,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      }
      setExperiments([...experiments, newExp])
      form.resetFields()
      setShowForm(false)
      message.success('实验记录已添加')
    } catch (e) {
      // validation error
    }
  }

  const handleConfirm = () => {
    if (experiments.length === 0) {
      message.warning('请至少添加一条实验记录')
      return
    }
    onComplete(experiments)
  }

  const columns = [
    { title: '实验编号', dataIndex: 'experiment_no', key: 'experiment_no', width: 130 },
    { title: '标题', dataIndex: 'title', key: 'title', width: 180 },
    { title: '操作人', dataIndex: 'operator', key: 'operator', width: 80 },
    { title: '收率', dataIndex: 'yield', key: 'yield', width: 80, render: (v: number) => v ? `${v}%` : '-' },
    { title: '纯度', dataIndex: 'purity', key: 'purity', width: 80, render: (v: number) => v ? `${v}%` : '-' },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: (s: string) => <Tag color={statusMap[s]?.color}>{statusMap[s]?.label}</Tag>,
    },
    { title: '日期', dataIndex: 'date', key: 'date', width: 110 },
  ]

  return (
    <div>
      {/* 实验方案参考 */}
      {experimentPlan && (
        <Card 
          title={<span><FileTextOutlined /> 实验方案参考 — {experimentPlan.route_name}</span>}
          style={{ marginBottom: 16 }}
          size="small"
        >
          <Alert
            title="请按照以下方案进行实验，实验完成后在此录入数据"
            description={`预计周期：${experimentPlan.estimated_duration} | 共 ${experimentPlan.steps.length} 个步骤`}
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
          />

          <Collapse 
            size="small"
            items={[
              {
                key: 'steps',
                label: `实验步骤（${experimentPlan.steps.length}步）`,
                children: experimentPlan.steps.map(step => (
                  <div key={step.step_no} style={{ marginBottom: 12, padding: 12, background: '#fafafa', borderRadius: 4 }}>
                    <div style={{ fontWeight: 600 }}>步骤{step.step_no}：{step.description}</div>
                    <div style={{ fontSize: 13, color: '#666', marginTop: 4 }}>
                      <div><b>试剂：</b>{step.reagents.join('、')}</div>
                      <div><b>条件：</b>{step.conditions}</div>
                      <div><b>预计收率：</b>{step.expected_yield}% | <b>耗时：</b>{step.duration}</div>
                      {step.notes && <div><b>备注：</b>{step.notes}</div>}
                    </div>
                  </div>
                )),
              },
              {
                key: 'analysis',
                label: `分析方法（${experimentPlan.analysis_methods.length}项）`,
                children: (
                  <Table
                    size="small"
                    pagination={false}
                    dataSource={experimentPlan.analysis_methods}
                    rowKey="name"
                    columns={[
                      { title: '方法', dataIndex: 'name', width: 80 },
                      { title: '目的', dataIndex: 'purpose', width: 100 },
                      { title: '方法详情', dataIndex: 'method' },
                      { title: '设备', dataIndex: 'equipment', width: 160 },
                    ]}
                  />
                ),
              },
              {
                key: 'materials',
                label: `物料清单（${experimentPlan.materials.length}种）`,
                children: (
                  <Table
                    size="small"
                    pagination={false}
                    dataSource={experimentPlan.materials}
                    rowKey="name"
                    columns={[
                      { title: '物料', dataIndex: 'name', width: 120 },
                      { title: '数量', dataIndex: 'quantity', width: 80 },
                      { title: '纯度', dataIndex: 'purity', width: 80 },
                      { title: '供应商', dataIndex: 'supplier', width: 100 },
                      { title: '到货周期', dataIndex: 'lead_time', width: 100 },
                    ]}
                  />
                ),
              },
              {
                key: 'safety',
                label: '安全注意事项',
                children: experimentPlan.safety_notes.map((note, i) => (
                  <div key={i} style={{ marginBottom: 4 }}>
                    <WarningOutlined style={{ color: '#ff4d4f', marginRight: 8 }} />
                    {note}
                  </div>
                )),
              },
            ]}
          />
        </Card>
      )}

      {/* 实验数据录入 */}
      <Card title={`🧪 实验数据录入 — ${selectedRouteName}`} style={{ marginBottom: 16 }}>
        <Alert
          title="录入实验数据"
          description="按照实验方案完成实验后，在此录入每条实验的结果数据。支持手动录入或上传实验记录图片由LLM辅助提取。"
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
        />

        <div style={{ marginBottom: 16 }}>
          <Space>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setShowForm(true)}>
              ➕ 添加实验记录
            </Button>
            <Upload
              multiple
              accept=".png,.jpg,.jpeg,.pdf"
              fileList={experimentFiles}
              beforeUpload={() => false}
              onChange={({ fileList }) => {
                setExperimentFiles(fileList)
                if (fileList.length > 0) {
                  message.success(`已选择 ${fileList.length} 个文件，点击"LLM智能提取"处理`)
                }
              }}
              onRemove={(file) => {
                setExperimentFiles(prev => prev.filter(f => f.uid !== file.uid))
              }}
            >
              <Button icon={<UploadOutlined />}>上传实验记录/图谱</Button>
            </Upload>
            <Button 
              icon={<RobotOutlined />} 
              type="primary" 
              ghost
              disabled={experimentFiles.length === 0}
              onClick={() => {
                message.loading({ content: 'LLM正在分析文件...', key: 'llm-extract', duration: 2 })
                setTimeout(() => {
                  message.success({ content: `已从 ${experimentFiles.length} 个文件中提取实验数据`, key: 'llm-extract' })
                  // 模拟提取结果
                  const mockExp: ExperimentRecord = {
                    id: `exp-${Date.now()}`,
                    route_id: routeId,
                    experiment_no: `EXP-${new Date().getFullYear()}-${String(experiments.length + 1).padStart(3, '0')}`,
                    title: `从 ${experimentFiles[0]?.name || '文件'} 提取`,
                    description: 'LLM自动提取的实验数据',
                    date: new Date().toISOString().split('T')[0],
                    operator: 'LLM提取',
                    status: 'completed',
                    reaction_temp: '25°C',
                    reaction_time: '12h',
                    yield: 82,
                    purity: 97.5,
                    impurities: '未检出明显杂质',
                    result_summary: 'LLM从文件中提取的实验结果',
                    created_at: new Date().toISOString(),
                    updated_at: new Date().toISOString(),
                  }
                  setExperiments([...experiments, mockExp])
                  setExperimentFiles([])
                }, 2000)
              }}
            >
              🤖 LLM智能提取{experimentFiles.length > 0 ? ` (${experimentFiles.length}个文件)` : ''}
            </Button>
          </Space>
        </div>

        {showForm && (
          <Card size="small" style={{ marginBottom: 16, backgroundColor: '#fafafa' }}>
            <Form form={form} layout="inline">
              <Form.Item name="title" label="标题" rules={[{ required: true }]}><Input placeholder="实验标题" /></Form.Item>
              <Form.Item name="operator" label="操作人" rules={[{ required: true }]}><Input placeholder="操作人" /></Form.Item>
              <Form.Item name="date" label="日期" rules={[{ required: true }]}><DatePicker /></Form.Item>
              <Form.Item name="status" label="状态" initialValue="completed">
                <Select style={{ width: 100 }} options={[
                  { value: 'planned', label: '计划中' },
                  { value: 'in_progress', label: '进行中' },
                  { value: 'completed', label: '已完成' },
                  { value: 'failed', label: '失败' },
                ]} />
              </Form.Item>
              <Form.Item name="reaction_temp" label="温度"><Input placeholder="25°C" style={{ width: 80 }} /></Form.Item>
              <Form.Item name="reaction_time" label="时间"><Input placeholder="12h" style={{ width: 80 }} /></Form.Item>
              <Form.Item name="yield" label="收率(%)"><Input type="number" placeholder="85" style={{ width: 70 }} /></Form.Item>
              <Form.Item name="purity" label="纯度(%)"><Input type="number" placeholder="98" style={{ width: 70 }} /></Form.Item>
              <Form.Item name="result_summary" label="结果摘要" style={{ width: 200 }}><Input placeholder="结果摘要" /></Form.Item>
              <Form.Item>
                <Space>
                  <Button type="primary" onClick={handleAddExperiment}>保存</Button>
                  <Button onClick={() => setShowForm(false)}>取消</Button>
                </Space>
              </Form.Item>
            </Form>
          </Card>
        )}

        {experiments.length > 0 ? (
          <Table
            columns={columns}
            dataSource={experiments}
            rowKey="id"
            pagination={false}
            size="small"
            scroll={{ x: 900 }}
          />
        ) : (
          <Alert
            title="暂无实验记录"
            description="请按照实验方案完成实验后，点击【添加实验记录】录入数据"
            type="warning"
            showIcon
          />
        )}

        {experiments.length > 0 && (
          <Alert
            title="⚠️ LLM异常检测"
            description={
              <ul style={{ margin: 0, paddingLeft: 20 }}>
                {experiments.filter(e => e.yield && e.yield < 70).map(e => (
                  <li key={e.id}>{e.experiment_no} 收率偏低（{e.yield}%），建议优化反应条件</li>
                ))}
                {experiments.filter(e => e.purity && e.purity < 95).map(e => (
                  <li key={e.id}>{e.experiment_no} 纯度偏低（{e.purity}%），建议改进纯化方法</li>
                ))}
                {experiments.filter(e => e.status === 'failed').map(e => (
                  <li key={e.id}>{e.experiment_no} 实验失败，请分析原因后重试</li>
                ))}
                {experiments.every(e => e.yield && e.yield >= 70 && e.purity && e.purity >= 95 && e.status !== 'failed') && (
                  <li>所有实验数据正常，可以继续</li>
                )}
              </ul>
            }
            type="warning"
            showIcon
            icon={<WarningOutlined />}
            style={{ marginTop: 16 }}
          />
        )}
      </Card>

      <Card>
        <Space>
          <Button type="primary" icon={<CheckCircleOutlined />} onClick={handleConfirm} size="large">
            ✓ 确认并进入下一步（四维度评估）
          </Button>
          <Button onClick={() => setShowForm(true)}>➕ 添加实验记录</Button>
        </Space>
      </Card>
    </div>
  )
}
