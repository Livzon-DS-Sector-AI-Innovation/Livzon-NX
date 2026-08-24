'use client'

import { useState, useCallback, useEffect } from 'react'
import { Table, Input, Select, DatePicker, Button, Space, Tag, Card, Statistic, Row, Col, Modal, App, Form, InputNumber, Checkbox, Upload, Progress, Alert, Descriptions } from 'antd'
import { SearchOutlined, CheckCircleOutlined, CloseCircleOutlined, BarChartOutlined, PlusOutlined, UploadOutlined, LoadingOutlined, RobotOutlined, EyeOutlined } from '@ant-design/icons'
import { LabelVerification, LabelVerificationCreateInput } from '@/types/label-verification'
import { fetchLabelVerifications, fetchLabelVerificationStatistics, createLabelVerification, autoCompareVideo, AutoCompareResult } from '@/lib/api/label-verification'
import dayjs from 'dayjs'

const { RangePicker } = DatePicker
const { Option } = Select

interface LabelVerificationClientProps {
  initialVerifications: LabelVerification[]
  initialTotal: number
  initialError?: string
}

export default function LabelVerificationClient({
  initialVerifications,
  initialTotal,
  initialError,
}: LabelVerificationClientProps) {
  const { message } = App.useApp()

  const [verifications, setVerifications] = useState<LabelVerification[]>(initialVerifications)
  const [total, setTotal] = useState(initialTotal)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [loading, setLoading] = useState(false)
  const [batchNumber, setBatchNumber] = useState('')
  const [productName, setProductName] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs | null, dayjs.Dayjs | null] | null>(null)
  const [statistics, setStatistics] = useState<any>(null)
  const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [createForm] = Form.useForm()
  const [videoUploading, setVideoUploading] = useState(false)
  const [selectedRecord, setSelectedRecord] = useState<LabelVerification | null>(null)

  // 自动对比相关状态
  const [autoComparing, setAutoComparing] = useState(false)
  const [autoCompareResult, setAutoCompareResult] = useState<AutoCompareResult | null>(null)
  const [autoCompareProgress, setAutoCompareProgress] = useState('')

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetchLabelVerifications({
        batch_number: batchNumber || undefined,
        product_name: productName || undefined,
        result_status: filterStatus || undefined,
        start_date: dateRange?.[0]?.format('YYYY-MM-DD'),
        end_date: dateRange?.[1]?.format('YYYY-MM-DD'),
        page,
        page_size: pageSize,
      })
      setVerifications(res.data)
      setTotal(res.meta?.total || 0)
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '加载数据失败')
    } finally {
      setLoading(false)
    }
  }, [batchNumber, productName, filterStatus, dateRange, page, pageSize])

  const loadStatistics = useCallback(async () => {
    try {
      const res = await fetchLabelVerificationStatistics()
      setStatistics(res.data)
    } catch (err) {
      console.error('加载统计数据失败', err)
    }
  }, [])

  useEffect(() => {
    loadData()
    loadStatistics()
  }, [loadData, loadStatistics])

  const handlePageChange = (newPage: number, newPageSize: number) => {
    setPage(newPage)
    setPageSize(newPageSize)
  }

  const handleVideoUpload = async (file: File) => {
    setVideoUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await fetch(`/api/v1/quality/label-verifications/upload-video`, {
        method: 'POST',
        body: formData,
      })
      if (!res.ok) throw new Error('上传失败')
      const result = await res.json()
      createForm.setFieldsValue({
        video_file_key: result.data.file_key,
        video_file_name: result.data.file_name,
      })
      message.success('视频上传成功')
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '上传失败')
    } finally {
      setVideoUploading(false)
    }
    return false
  }

  // ─── 自动对比 ───

  const handleAutoCompare = async () => {
    try {
      const values = await createForm.validateFields([
        'video_file_key', 'batch_number', 'product_name',
        'production_date', 'expiry_date',
        'total_barrels', 'standard_barrels', 'remainder_barrel',
        'standard_weight', 'remainder_weight', 'total_weight',
      ])

      setAutoComparing(true)
      setAutoCompareResult(null)
      setAutoCompareProgress('正在分析视频，提取标签信息...')

      const result = await autoCompareVideo({
        video_file_key: values.video_file_key,
        batch_number: values.batch_number,
        product_name: values.product_name,
        production_date: values.production_date.format('YYYY-MM-DD'),
        expiry_date: values.expiry_date.format('YYYY-MM-DD'),
        total_barrels: values.total_barrels,
        standard_barrels: values.standard_barrels,
        remainder_barrel: values.remainder_barrel,
        standard_weight: values.standard_weight,
        remainder_weight: values.remainder_weight,
        total_weight: values.total_weight,
      })

      setAutoCompareProgress('')
      const compareData = result.data
      setAutoCompareResult(compareData)

      // 自动填充 8 项核对结论
      createForm.setFieldsValue({
        check_batch_number: compareData.checks.check_batch_number,
        check_production_date: compareData.checks.check_production_date,
        check_expiry_date: compareData.checks.check_expiry_date,
        check_standard_barrels: compareData.checks.check_standard_barrels,
        check_remainder_barrel: compareData.checks.check_remainder_barrel,
        check_total_weight: compareData.checks.check_total_weight,
        check_all_barrels_identified: compareData.checks.check_all_barrels_identified,
        check_exception_handled: compareData.checks.check_exception_handled,
        result_status: compareData.result_status,
        result_summary: compareData.result_summary,
      })

      if (compareData.confidence >= 70) {
        message.success(`自动对比完成，置信度 ${compareData.confidence}%`)
      } else {
        message.warning(`对比完成但置信度较低 (${compareData.confidence}%)，建议人工复核`)
      }
    } catch (err) {
      setAutoCompareProgress('')
      if ((typeof err === 'object' && err !== null && 'errorFields' in err)) {
        message.warning('请先填写表单基本信息并上传视频')
      } else {
        message.error((err instanceof Error ? err.message : '') || '自动对比失败')
      }
    } finally {
      setAutoComparing(false)
    }
  }

  const handleCreate = async (values: any) => {
    try {
      const data: LabelVerificationCreateInput = {
        batch_number: values.batch_number,
        product_name: values.product_name,
        production_date: values.production_date.format('YYYY-MM-DD'),
        expiry_date: values.expiry_date.format('YYYY-MM-DD'),
        total_barrels: values.total_barrels,
        standard_barrels: values.standard_barrels,
        remainder_barrel: values.remainder_barrel,
        standard_weight: values.standard_weight,
        remainder_weight: values.remainder_weight,
        total_weight: values.total_weight,
        check_batch_number: values.check_batch_number,
        check_production_date: values.check_production_date,
        check_expiry_date: values.check_expiry_date,
        check_standard_barrels: values.check_standard_barrels,
        check_remainder_barrel: values.check_remainder_barrel,
        check_total_weight: values.check_total_weight,
        check_all_barrels_identified: values.check_all_barrels_identified,
        check_exception_handled: values.check_exception_handled,
        result_status: values.result_status,
        result_summary: values.result_summary,
        video_file_key: values.video_file_key,
        video_file_name: values.video_file_name,
        verification_date: values.verification_date.format('YYYY-MM-DD'),
        verification_time: values.verification_time.format('YYYY-MM-DDTHH:mm:ss'),
        remarks: values.remarks,
      }
      await createLabelVerification(data)
      message.success('创建成功')
      setCreateModalOpen(false)
      createForm.resetFields()
      setAutoCompareResult(null)
      loadData()
      loadStatistics()
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '创建失败')
    }
  }

  const showDetail = (record: LabelVerification) => {
    setSelectedRecord(record)
    setDetailModalOpen(true)
  }

  const columns = [
    {
      title: '批号',
      dataIndex: 'batch_number',
      key: 'batch_number',
      width: 120,
    },
    {
      title: '产品名称',
      dataIndex: 'product_name',
      key: 'product_name',
      width: 150,
    },
    {
      title: '生产日期',
      dataIndex: 'production_date',
      key: 'production_date',
      width: 110,
      render: (date: string) => dayjs(date).format('YYYY-MM-DD'),
    },
    {
      title: '有效期至',
      dataIndex: 'expiry_date',
      key: 'expiry_date',
      width: 110,
      render: (date: string) => dayjs(date).format('YYYY-MM-DD'),
    },
    {
      title: '桶数',
      dataIndex: 'total_barrels',
      key: 'total_barrels',
      width: 80,
      align: 'center' as const,
      render: (val: number) => `${val}桶`,
    },
    {
      title: '总重量',
      dataIndex: 'total_weight',
      key: 'total_weight',
      width: 100,
      align: 'center' as const,
      render: (val: number) => `${val}kg`,
    },
    {
      title: '复核结论',
      dataIndex: 'result_status',
      key: 'result_status',
      width: 120,
      render: (status: string) => (
        <Tag color={status === '全部一致' ? 'success' : 'error'}>
          {status}
        </Tag>
      ),
    },
    {
      title: '复核时间',
      dataIndex: 'verification_time',
      key: 'verification_time',
      width: 160,
      render: (time: string) => dayjs(time).format('YYYY-MM-DD HH:mm'),
    },
    {
      title: '操作',
      key: 'action',
      width: 80,
      fixed: 'right' as const,
      render: (_: any, record: LabelVerification) => (
        <Button type="link" size="small" onClick={() => showDetail(record)}>
          详情
        </Button>
      ),
    },
  ]

  const CheckItem = ({ label, passed }: { label: string; passed: boolean }) => (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
      {passed ? (
        <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 16 }} />
      ) : (
        <CloseCircleOutlined style={{ color: '#ff4d4f', fontSize: 16 }} />
      )}
      <span>{label}</span>
      <Tag color={passed ? 'success' : 'error'}>{passed ? '一致' : '不一致'}</Tag>
    </div>
  )

  // 自动对比结果展示组件
  const AutoCompareResultPanel = ({ result }: { result: AutoCompareResult }) => {
    const checkLabels: Record<string, string> = {
      check_batch_number: '1. 标签批号对比',
      check_production_date: '2. 每桶生产日期对比',
      check_expiry_date: '3. 每桶有效期至对比',
      check_standard_barrels: '4. 整桶数量/桶号/重量对比',
      check_remainder_barrel: '5. 零头数量/桶号/重量对比',
      check_total_weight: '6. 总重量对比',
      check_all_barrels_identified: '7. 是否识别到每一桶',
      check_exception_handled: '8. 异常处理',
    }

    return (
      <div style={{ background: '#fafafa', borderRadius: 8, padding: 16, marginTop: 8, marginBottom: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <strong><RobotOutlined /> AI 自动对比结果</strong>
          <Space>
            <Tag color={result.confidence >= 70 ? 'success' : result.confidence >= 50 ? 'warning' : 'error'}>
              置信度 {result.confidence}%
            </Tag>
            <Tag>提取 {result.frames_count} 帧</Tag>
            {result.retry_count > 0 && <Tag color="orange">重试 {result.retry_count} 次</Tag>}
          </Space>
        </div>

        {/* 8项结论 */}
        <div style={{ marginBottom: 12 }}>
          {Object.entries(result.checks).map(([key, passed]) => (
            <div key={key} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              {passed ? (
                <CheckCircleOutlined style={{ color: '#52c41a' }} />
              ) : (
                <CloseCircleOutlined style={{ color: '#ff4d4f' }} />
              )}
              <span style={{ fontSize: 13 }}>{checkLabels[key] || key}</span>
              {result.reasons?.[key] && (
                <span style={{ fontSize: 12, color: '#999', marginLeft: 4 }}>
                  — {result.reasons[key]}
                </span>
              )}
            </div>
          ))}
        </div>

        {/* AI 识别到的数据 */}
        <Descriptions size="small" column={3} bordered style={{ fontSize: 12 }}>
          <Descriptions.Item label="AI识别批号">{result.ai_data.batch_number || '未识别'}</Descriptions.Item>
          <Descriptions.Item label="AI识别生产日期">{result.ai_data.production_date || '未识别'}</Descriptions.Item>
          <Descriptions.Item label="AI识别有效期至">{result.ai_data.expiry_date || '未识别'}</Descriptions.Item>
          <Descriptions.Item label="AI识别总桶数">{result.ai_data.total_barrels ?? '未识别'}</Descriptions.Item>
          <Descriptions.Item label="AI识别整桶数">{result.ai_data.standard_barrels ?? '未识别'}</Descriptions.Item>
          <Descriptions.Item label="AI识别总重量">{result.ai_data.total_weight != null ? `${result.ai_data.total_weight}kg` : '未识别'}</Descriptions.Item>
        </Descriptions>

        {result.notes && (
          <Alert type="info" message={result.notes} style={{ marginTop: 8 }} showIcon />
        )}

        {result.confidence < 70 && (
          <Alert
            type="warning"
            message="置信度较低，建议人工复核"
            description="AI 识别不够清晰，已自动降低帧率多次尝试，但仍建议人工确认结果。"
            style={{ marginTop: 8 }}
            showIcon
          />
        )}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {initialError && (
        <Alert
          type="warning"
          showIcon
          message="标签复核数据暂时无法加载"
          description={initialError}
        />
      )}
      {/* 统计卡片 */}
      {statistics && (
        <Row gutter={16}>
          <Col span={6}>
            <Card>
              <Statistic title="总复核次数" value={statistics.total} prefix={<BarChartOutlined />} />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="全部一致"
                value={statistics.all_match}
                styles={{ content: { color: '#52c41a' } }}
                prefix={<CheckCircleOutlined />}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="存在差异"
                value={statistics.has_difference}
                styles={{ content: { color: '#ff4d4f' } }}
                prefix={<CloseCircleOutlined />}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card>
              <Statistic
                title="一致率"
                value={statistics.match_rate}
                precision={1}
                suffix="%"
                styles={{ content: { color: statistics.match_rate >= 90 ? '#52c41a' : '#faad14' } }}
              />
            </Card>
          </Col>
        </Row>
      )}

      {/* 筛选和表格 */}
      <Card>
        <Space style={{ marginBottom: 16 }} wrap>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalOpen(true)}>
            新增
          </Button>
          <Input
            placeholder="批号搜索"
            prefix={<SearchOutlined />}
            value={batchNumber}
            onChange={(e) => setBatchNumber(e.target.value)}
            style={{ width: 180 }}
            allowClear
          />
          <Input
            placeholder="产品名称搜索"
            value={productName}
            onChange={(e) => setProductName(e.target.value)}
            style={{ width: 180 }}
            allowClear
          />
          <Select
            placeholder="结论状态"
            value={filterStatus || undefined}
            onChange={(val) => setFilterStatus(val || '')}
            style={{ width: 140 }}
            allowClear
          >
            <Option value="全部一致">全部一致</Option>
            <Option value="存在差异">存在差异</Option>
          </Select>
          <RangePicker
            value={dateRange}
            onChange={(dates) => setDateRange(dates as any)}
            placeholder={['复核开始日期', '复核结束日期']}
          />
        </Space>

        <Table
          columns={columns}
          dataSource={verifications}
          rowKey="id"
          loading={loading}
          pagination={{
            current: page,
            pageSize: pageSize,
            total: total,
            showSizeChanger: true,
            showTotal: (total) => `共 ${total} 条`,
            onChange: handlePageChange,
          }}
          scroll={{ x: 1200 }}
        />
      </Card>

      {/* 新增弹窗 */}
      <Modal
        title="新增标签复核记录"
        open={createModalOpen}
        onCancel={() => { setCreateModalOpen(false); createForm.resetFields(); setAutoCompareResult(null) }}
        onOk={() => createForm.submit()}
        width={850}
        okText="保存"
        cancelText="取消"
      >
        <Form
          form={createForm}
          layout="vertical"
          onFinish={handleCreate}
          style={{ maxHeight: '70vh', overflow: 'auto', paddingRight: 8 }}
        >
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="batch_number" label="批号" rules={[{ required: true, message: '请输入批号' }]}>
                <Input placeholder="如 QS32603006" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="product_name" label="产品名称" rules={[{ required: true, message: '请输入产品名称' }]}>
                <Input placeholder="产品名称" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="production_date" label="生产日期" rules={[{ required: true, message: '请选择生产日期' }]}>
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="expiry_date" label="有效期至" rules={[{ required: true, message: '请选择有效期' }]}>
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="total_barrels" label="总桶数" rules={[{ required: true }]}>
                <InputNumber min={1} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="standard_barrels" label="整桶数" rules={[{ required: true }]}>
                <InputNumber min={0} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="remainder_barrel" label="零头桶数" rules={[{ required: true }]}>
                <InputNumber min={0} max={1} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="standard_weight" label="整桶重量(kg)" rules={[{ required: true }]}>
                <InputNumber min={0} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="remainder_weight" label="零头重量(kg)" rules={[{ required: true }]}>
                <InputNumber min={0} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="total_weight" label="总重量(kg)" rules={[{ required: true }]}>
                <InputNumber min={0} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>

          {/* 视频上传 */}
          <Row gutter={16}>
            <Col span={24}>
              <Form.Item label="上传视频" required>
                <Upload.Dragger
                  name="file"
                  accept="video/*"
                  showUploadList={false}
                  beforeUpload={handleVideoUpload}
                  disabled={videoUploading || autoComparing}
                >
                  <p className="ant-upload-drag-icon">
                    {videoUploading ? <LoadingOutlined /> : <UploadOutlined />}
                  </p>
                  <p className="ant-upload-text">点击或拖拽视频文件到此区域上传</p>
                  <p className="ant-upload-hint">支持 MP4、AVI、MOV 等视频格式</p>
                </Upload.Dragger>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="video_file_key" hidden>
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="video_file_name" label="视频文件名">
                <Input placeholder="上传后自动填充" readOnly />
              </Form.Item>
            </Col>
          </Row>

          {/* 自动对比按钮 */}
          <Form.Item noStyle shouldUpdate={(prev, cur) => prev.video_file_key !== cur.video_file_key}>
            {({ getFieldValue }) => {
              const hasVideo = !!getFieldValue('video_file_key')
              return (
                <div style={{ marginBottom: 16 }}>
                  <Button
                    type="primary"
                    icon={autoComparing ? <LoadingOutlined /> : <RobotOutlined />}
                    onClick={handleAutoCompare}
                    disabled={!hasVideo || autoComparing}
                    loading={autoComparing}
                    block
                    size="large"
                    style={{ marginBottom: 8 }}
                  >
                    {autoComparing ? '正在分析视频...' : '自动对比（AI 分析视频与表单数据）'}
                  </Button>
                  {autoComparing && (
                    <div style={{ textAlign: 'center', color: '#666', fontSize: 13 }}>
                      <LoadingOutlined style={{ marginRight: 8 }} />
                      {autoCompareProgress || 'AI 正在识别标签信息，请稍候...'}
                    </div>
                  )}
                </div>
              )
            }}
          </Form.Item>

          {/* 自动对比结果 */}
          {autoCompareResult && <AutoCompareResultPanel result={autoCompareResult} />}

          {/* 8项核对结论（可手动修改） */}
          <div style={{ marginBottom: 16, fontWeight: 600 }}>
            8项核对结论
            <span style={{ fontSize: 12, color: '#999', fontWeight: 'normal', marginLeft: 8 }}>
              （可通过自动对比填充，也可手动修改）
            </span>
          </div>
          <Row gutter={[16, 8]}>
            <Col span={12}><Form.Item name="check_batch_number" valuePropName="checked" initialValue={true}><Checkbox>1. 标签批号对比</Checkbox></Form.Item></Col>
            <Col span={12}><Form.Item name="check_production_date" valuePropName="checked" initialValue={true}><Checkbox>2. 每桶生产日期对比</Checkbox></Form.Item></Col>
            <Col span={12}><Form.Item name="check_expiry_date" valuePropName="checked" initialValue={true}><Checkbox>3. 每桶有效期至对比</Checkbox></Form.Item></Col>
            <Col span={12}><Form.Item name="check_standard_barrels" valuePropName="checked" initialValue={true}><Checkbox>4. 整桶数量/桶号/重量对比</Checkbox></Form.Item></Col>
            <Col span={12}><Form.Item name="check_remainder_barrel" valuePropName="checked" initialValue={true}><Checkbox>5. 零头数量/桶号/重量对比</Checkbox></Form.Item></Col>
            <Col span={12}><Form.Item name="check_total_weight" valuePropName="checked" initialValue={true}><Checkbox>6. 总重量对比</Checkbox></Form.Item></Col>
            <Col span={12}><Form.Item name="check_all_barrels_identified" valuePropName="checked" initialValue={true}><Checkbox>7. 是否识别到每一桶</Checkbox></Form.Item></Col>
            <Col span={12}><Form.Item name="check_exception_handled" valuePropName="checked" initialValue={true}><Checkbox>8. 异常处理</Checkbox></Form.Item></Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="result_status" label="总体结论" rules={[{ required: true }]}>
                <Select>
                  <Option value="全部一致">全部一致</Option>
                  <Option value="存在差异">存在差异</Option>
                </Select>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="result_summary" label="结论摘要" rules={[{ required: true }]}>
                <Input placeholder="如 ✅✅✅ 全部一致" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="verification_date" label="复核日期" rules={[{ required: true }]}>
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="verification_time" label="复核时间" rules={[{ required: true }]}>
                <DatePicker showTime style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="remarks" label="备注">
            <Input.TextArea rows={2} placeholder="备注信息" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 详情弹窗 */}
      <Modal
        title="标签复核详情"
        open={detailModalOpen}
        onCancel={() => setDetailModalOpen(false)}
        footer={[
          <Button key="close" onClick={() => setDetailModalOpen(false)}>
            关闭
          </Button>,
        ]}
        width={700}
      >
        {selectedRecord && (
          <div>
            <Row gutter={[16, 16]}>
              <Col span={12}>
                <strong>批号：</strong>{selectedRecord.batch_number}
              </Col>
              <Col span={12}>
                <strong>产品名称：</strong>{selectedRecord.product_name}
              </Col>
              <Col span={12}>
                <strong>生产日期：</strong>{dayjs(selectedRecord.production_date).format('YYYY-MM-DD')}
              </Col>
              <Col span={12}>
                <strong>有效期至：</strong>{dayjs(selectedRecord.expiry_date).format('YYYY-MM-DD')}
              </Col>
              <Col span={12}>
                <strong>总桶数：</strong>{selectedRecord.total_barrels}桶（整桶{selectedRecord.standard_barrels} + 零头{selectedRecord.remainder_barrel}）
              </Col>
              <Col span={12}>
                <strong>总重量：</strong>{selectedRecord.total_weight}kg
              </Col>
              <Col span={12}>
                <strong>整桶重量：</strong>{selectedRecord.standard_weight}kg
              </Col>
              <Col span={12}>
                <strong>零头重量：</strong>{selectedRecord.remainder_weight}kg
              </Col>
            </Row>

            <div style={{ marginTop: 24, marginBottom: 16 }}>
              <strong>8项核对结论：</strong>
            </div>
            <div style={{ paddingLeft: 8 }}>
              <CheckItem label="1. 标签批号对比" passed={selectedRecord.check_batch_number} />
              <CheckItem label="2. 每桶生产日期对比" passed={selectedRecord.check_production_date} />
              <CheckItem label="3. 每桶有效期至对比" passed={selectedRecord.check_expiry_date} />
              <CheckItem label="4. 整桶数量/桶号/重量对比" passed={selectedRecord.check_standard_barrels} />
              <CheckItem label="5. 零头数量/桶号/重量对比" passed={selectedRecord.check_remainder_barrel} />
              <CheckItem label="6. 总重量对比" passed={selectedRecord.check_total_weight} />
              <CheckItem label="7. 是否识别到每一桶" passed={selectedRecord.check_all_barrels_identified} />
              <CheckItem label="8. 异常处理" passed={selectedRecord.check_exception_handled} />
            </div>

            <div style={{ marginTop: 24 }}>
              <strong>总体结论：</strong>
              <Tag color={selectedRecord.result_status === '全部一致' ? 'success' : 'error'} style={{ marginLeft: 8 }}>
                {selectedRecord.result_summary}
              </Tag>
            </div>

            {selectedRecord.video_file_name && (
              <div style={{ marginTop: 16 }}>
                <strong>视频来源：</strong>{selectedRecord.video_file_name}
                {selectedRecord.video_frame_count && ` (${selectedRecord.video_frame_count}帧 @ ${selectedRecord.video_fps}fps)`}
              </div>
            )}

            <div style={{ marginTop: 8 }}>
              <strong>复核时间：</strong>{dayjs(selectedRecord.verification_time).format('YYYY-MM-DD HH:mm:ss')}
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}
