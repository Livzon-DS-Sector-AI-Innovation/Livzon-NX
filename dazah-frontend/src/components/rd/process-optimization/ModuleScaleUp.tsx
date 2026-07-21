'use client'

import { useState } from 'react'
import { Card, Button, Space, Tag, Table, Form, Input, InputNumber, Select, App, Tabs, Alert, Row, Col, Statistic, Descriptions } from 'antd'
import { CheckCircleOutlined, PlusOutlined, ExpandOutlined } from '@ant-design/icons'
import type { ScaleUpStudy, ScaleUpBatch, DOEExperiment, LabConfirmationStudy } from '@/types/rd'
import { AIFileParser } from './AIFileParser'

interface ModuleScaleUpProps {
  optimizationId: string
  doeExperiment?: DOEExperiment
  labConfirmationStudy?: LabConfirmationStudy
  initialData?: ScaleUpStudy
  onComplete: (study: ScaleUpStudy) => void
}

export function ModuleScaleUp({ optimizationId, doeExperiment, labConfirmationStudy, initialData, onComplete }: ModuleScaleUpProps) {
  const { message } = App.useApp()
  const [activeTab, setActiveTab] = useState('plan')
  const [targetScale, setTargetScale] = useState(initialData?.target_scale_kg || 5)
  const [materialBalance, setMaterialBalance] = useState(initialData?.material_balance || '')
  const [equipmentSelection, setEquipmentSelection] = useState(initialData?.equipment_selection || '')
  const [parameterAdjustments, setParameterAdjustments] = useState(initialData?.parameter_adjustments || '')
  const [batch, setBatch] = useState<ScaleUpBatch | undefined>(initialData?.batch)
  const [comparisonSummary, setComparisonSummary] = useState(initialData?.comparison_summary || '')
  const [conclusion, setConclusion] = useState(initialData?.conclusion || '')
  const [showForm, setShowForm] = useState(!initialData?.batch)
  const [form] = Form.useForm()

  const handleSaveBatch = async () => {
    try {
      const values = await form.validateFields()
      const newBatch: ScaleUpBatch = {
        id: `batch-${Date.now()}`,
        batch_no: values.batch_no || `SU-${new Date().getFullYear()}-${String(Date.now()).slice(-4)}`,
        scale_kg: values.scale_kg,
        date: values.date,
        operator: values.operator,
        equipment: values.equipment,
        parameters: {},
        yield_pct: values.yield_pct,
        purity_pct: values.purity_pct,
        impurities_pct: values.impurities_pct,
        appearance: values.appearance,
        comparison_notes: values.comparison_notes,
        status: values.status || 'completed',
      }
      setBatch(newBatch)
      form.resetFields()
      setShowForm(false)
      message.success('批次记录已保存')
    } catch {}
  }

  const handleConfirm = () => {
    const study: ScaleUpStudy = {
      id: `scaleup-${optimizationId}`,
      target_scale_kg: targetScale,
      lab_confirmation_study_id: labConfirmationStudy?.id,
      material_balance: materialBalance,
      equipment_selection: equipmentSelection,
      parameter_adjustments: parameterAdjustments,
      batch: batch,
      comparison_summary: comparisonSummary,
      conclusion: conclusion || `公斤级放大试验完成，目标规模${targetScale}kg。`,
    }
    onComplete(study)
  }

  const tabItems = [
    {
      key: 'plan',
      label: '放大方案',
      children: (
        <div>
          <Alert
            type="info"
            showIcon
            title="公斤级放大试验"
            description="基于小试工艺确认批的结果，制定公斤级放大试验方案。通常只进行一批试验，验证工艺在放大规模下的可行性。"
            style={{ marginBottom: 16 }}
          />

          {labConfirmationStudy && (
            <Card type="inner" title="小试确认批参考数据" style={{ marginBottom: 16 }}>
              <Descriptions bordered column={2} size="small">
                <Descriptions.Item label="批号">{labConfirmationStudy.batch.batch_no}</Descriptions.Item>
                <Descriptions.Item label="规模">{labConfirmationStudy.batch.scale_g} g</Descriptions.Item>
                <Descriptions.Item label="收率">{labConfirmationStudy.batch.yield_pct}%</Descriptions.Item>
                <Descriptions.Item label="纯度">{labConfirmationStudy.batch.purity_pct}%</Descriptions.Item>
              </Descriptions>
              <div style={{ marginTop: 12 }}>
                <strong>小试结论：</strong>
                <div style={{ whiteSpace: 'pre-wrap', marginTop: 4 }}>{labConfirmationStudy.conclusion}</div>
              </div>
            </Card>
          )}

          <Form layout="vertical">
            <Form.Item label="目标放大规模 (kg)" required>
              <InputNumber
                value={targetScale}
                onChange={(v) => v && setTargetScale(v)}
                min={1}
                max={1000}
                style={{ width: '100%' }}
                placeholder="如：5 kg"
              />
            </Form.Item>

            <Form.Item label="物料平衡计算">
              <Input.TextArea
                value={materialBalance}
                onChange={(e) => setMaterialBalance(e.target.value)}
                rows={4}
                placeholder="根据小试确认批的投料量，计算公斤级规模的物料用量..."
              />
            </Form.Item>

            <Form.Item label="设备选型">
              <Input.TextArea
                value={equipmentSelection}
                onChange={(e) => setEquipmentSelection(e.target.value)}
                rows={3}
                placeholder="选择合适的反应釜/结晶釜，考虑容积、材质、搅拌方式等..."
              />
            </Form.Item>

            <Form.Item label="工艺参数调整">
              <Input.TextArea
                value={parameterAdjustments}
                onChange={(e) => setParameterAdjustments(e.target.value)}
                rows={6}
                placeholder="根据放大效应，调整温度、时间、搅拌速度等参数...

例如：
- 反应温度：小试70°C → 放大68-72°C（考虑传热差异）
- 搅拌速度：适当降低，避免剪切力过大
- 加料速度：延长加料时间，控制放热速率"
              />
            </Form.Item>
          </Form>

          <div style={{ textAlign: 'right', marginTop: 16 }}>
            <Button type="primary" onClick={() => setActiveTab('batch')}>
              下一步：记录试验数据 →
            </Button>
          </div>
        </div>
      ),
    },
    {
      key: 'batch',
      label: '试验记录',
      children: (
        <div>
          {!showForm && batch ? (
            <>
              <Card title="公斤级放大试验批次" style={{ marginBottom: 16 }}>
                <Descriptions bordered column={2}>
                  <Descriptions.Item label="批号">{batch.batch_no}</Descriptions.Item>
                  <Descriptions.Item label="规模">{batch.scale_kg} kg</Descriptions.Item>
                  <Descriptions.Item label="日期">{batch.date}</Descriptions.Item>
                  <Descriptions.Item label="操作人">{batch.operator}</Descriptions.Item>
                  <Descriptions.Item label="设备">{batch.equipment}</Descriptions.Item>
                  <Descriptions.Item label="外观">{batch.appearance}</Descriptions.Item>
                </Descriptions>

                <Row gutter={16} style={{ marginTop: 16 }}>
                  <Col span={8}>
                    <Statistic title="收率" value={batch.yield_pct} suffix="%" precision={1} />
                  </Col>
                  <Col span={8}>
                    <Statistic title="纯度" value={batch.purity_pct} suffix="%" precision={2} />
                  </Col>
                  <Col span={8}>
                    <Statistic title="杂质" value={batch.impurities_pct} suffix="%" precision={2} />
                  </Col>
                </Row>

                {batch.comparison_notes && (
                  <div style={{ marginTop: 16 }}>
                    <strong>备注：</strong>
                    <div style={{ whiteSpace: 'pre-wrap' }}>{batch.comparison_notes}</div>
                  </div>
                )}
              </Card>

              <div style={{ textAlign: 'right' }}>
                <Button onClick={() => setShowForm(true)}>修改批次数据</Button>
              </div>
            </>
          ) : (
            <>
            <AIFileParser
              parseType="scale_up"
              onParseComplete={(data) => {
                // 将AI解析的结果填充到表单
                form.setFieldsValue({
                  batch_no: data.batch_no,
                  scale_kg: data.scale_kg,
                  date: data.date,
                  operator: data.operator,
                  equipment: data.equipment,
                  yield_pct: data.yield_pct,
                  purity_pct: data.purity_pct,
                  impurities_pct: data.impurities_pct,
                  appearance: data.appearance,
                  comparison_notes: data.comparison_notes,
                })
                message.success('AI已自动填充表单，请检查并确认')
              }}
              hint="上传公斤级放大试验记录、批记录等文件，AI将自动识别并填充表单"
            />

            <Card title="录入公斤级放大试验数据">
              <Form form={form} layout="vertical" initialValues={batch}>
                <Form.Item name="batch_no" label="批号" rules={[{ required: true }]}>
                  <Input placeholder="如：SU-2026-001" />
                </Form.Item>

                <Row gutter={16}>
                  <Col span={12}>
                    <Form.Item name="scale_kg" label="规模 (kg)" rules={[{ required: true }]}>
                      <InputNumber min={0.1} max={1000} style={{ width: '100%' }} />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item name="date" label="日期" rules={[{ required: true }]}>
                      <Input type="date" />
                    </Form.Item>
                  </Col>
                </Row>

                <Row gutter={16}>
                  <Col span={12}>
                    <Form.Item name="operator" label="操作人" rules={[{ required: true }]}>
                      <Input />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item name="equipment" label="设备" rules={[{ required: true }]}>
                      <Input placeholder="如：100L反应釜" />
                    </Form.Item>
                  </Col>
                </Row>

                <Card type="inner" title="质量结果" style={{ marginBottom: 16 }}>
                  <Row gutter={16}>
                    <Col span={8}>
                      <Form.Item name="yield_pct" label="收率 (%)" rules={[{ required: true }]}>
                        <InputNumber min={0} max={100} precision={1} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                    <Col span={8}>
                      <Form.Item name="purity_pct" label="纯度 (%)" rules={[{ required: true }]}>
                        <InputNumber min={0} max={100} precision={2} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                    <Col span={8}>
                      <Form.Item name="impurities_pct" label="杂质 (%)">
                        <InputNumber min={0} max={10} precision={2} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                  </Row>

                  <Form.Item name="appearance" label="外观" rules={[{ required: true }]}>
                    <Input placeholder="如：白色结晶性粉末" />
                  </Form.Item>
                </Card>

                <Form.Item name="comparison_notes" label="与小试对比备注">
                  <Input.TextArea
                    rows={4}
                    placeholder="记录放大试验与小试的差异观察，如：
- 反应时间延长/缩短
- 收率变化原因
- 外观差异
- 其他异常情况"
                  />
                </Form.Item>

                <Form.Item>
                  <Button type="primary" onClick={handleSaveBatch} block>
                    保存批次数据
                  </Button>
                </Form.Item>
              </Form>
            </Card>
            </>
          )}

          <div style={{ textAlign: 'right', marginTop: 16 }}>
            <Button onClick={() => setActiveTab('plan')} style={{ marginRight: 8 }}>
              ← 上一步
            </Button>
            <Button type="primary" onClick={() => setActiveTab('comparison')} disabled={!batch}>
              下一步：对比分析 →
            </Button>
          </div>
        </div>
      ),
    },
    {
      key: 'comparison',
      label: '对比与结论',
      children: (
        <div>
          {labConfirmationStudy && batch && (
            <Card title="小试 vs 公斤级放大对比" style={{ marginBottom: 16 }}>
              <Table
                dataSource={[
                  {
                    key: 'scale',
                    item: '规模',
                    lab: `${labConfirmationStudy.batch.scale_g} g`,
                    scaleup: `${batch.scale_kg} kg`,
                    diff: `放大 ${Math.round(batch.scale_kg * 1000 / labConfirmationStudy.batch.scale_g)} 倍`,
                  },
                  {
                    key: 'yield',
                    item: '收率',
                    lab: `${labConfirmationStudy.batch.yield_pct}%`,
                    scaleup: `${batch.yield_pct}%`,
                    diff: `${(batch.yield_pct - labConfirmationStudy.batch.yield_pct).toFixed(1)}%`,
                  },
                  {
                    key: 'purity',
                    item: '纯度',
                    lab: `${labConfirmationStudy.batch.purity_pct}%`,
                    scaleup: `${batch.purity_pct}%`,
                    diff: `${(batch.purity_pct - labConfirmationStudy.batch.purity_pct).toFixed(2)}%`,
                  },
                ]}
                columns={[
                  { title: '指标', dataIndex: 'item', key: 'item' },
                  { title: '小试确认批', dataIndex: 'lab', key: 'lab' },
                  { title: '公斤级放大', dataIndex: 'scaleup', key: 'scaleup' },
                  { title: '差异', dataIndex: 'diff', key: 'diff' },
                ]}
                pagination={false}
                size="small"
              />
            </Card>
          )}

          <Form layout="vertical">
            <Form.Item label="关键指标对比总结">
              <Input.TextArea
                value={comparisonSummary}
                onChange={(e) => setComparisonSummary(e.target.value)}
                rows={4}
                placeholder="总结放大试验与小试的关键指标对比，分析差异原因..."
              />
            </Form.Item>

            <Form.Item label="结论">
              <Input.TextArea
                value={conclusion}
                onChange={(e) => setConclusion(e.target.value)}
                rows={6}
                placeholder="总结公斤级放大试验结果，说明工艺是否成功放大，是否存在需要进一步优化的问题..."
              />
            </Form.Item>
          </Form>

          <div style={{ textAlign: 'right', marginTop: 16 }}>
            <Button onClick={() => setActiveTab('batch')} style={{ marginRight: 8 }}>
              ← 上一步
            </Button>
            <Button type="primary" icon={<CheckCircleOutlined />} onClick={handleConfirm}>
              完成公斤级放大试验
            </Button>
          </div>
        </div>
      ),
    },
  ]

  return (
    <div>
      <Card
        title={
          <Space>
            <ExpandOutlined />
            公斤级放大试验
            <Tag color="blue">目标 {targetScale} kg</Tag>
            {batch && <Tag color="green">已完成</Tag>}
          </Space>
        }
      >
        <Tabs activeKey={activeTab} onChange={setActiveTab} items={tabItems} />
      </Card>
    </div>
  )
}
