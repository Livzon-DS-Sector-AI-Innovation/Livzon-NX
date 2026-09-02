'use client'

import { useState } from 'react'
import { Form, Input, Upload, Button, App, Card, Radio, Typography } from 'antd'
import {
  InboxOutlined, ArrowLeftOutlined, CheckCircleFilled,
  FileTextOutlined, AuditOutlined, SyncOutlined,
} from '@ant-design/icons'
import { useRouter } from 'next/navigation'
import type { AuditMode } from '@/types/validation-audit'
import {
  createValidationAuditTask,
  uploadValidationAuditFiles,
} from '@/actions/validation-audit'

const { Dragger } = Upload
const { Text } = Typography

const AUDIT_MODE_CARDS: { value: AuditMode; icon: React.ReactNode; title: string; desc: string; tint: string }[] = [
  {
    value: 'protocol',
    icon: <FileTextOutlined style={{ fontSize: 28 }} />,
    title: '验证方案审核',
    desc: '审核方案完整性、科学性、可执行性',
    tint: '#e6e0f5',
  },
  {
    value: 'report',
    icon: <AuditOutlined style={{ fontSize: 28 }} />,
    title: '验证报告审核',
    desc: '审核报告合规性、数据完整性、结论合理性',
    tint: '#dcecfa',
  },
  {
    value: 'protocol_report',
    icon: <SyncOutlined style={{ fontSize: 28 }} />,
    title: '方案 + 报告联合审核',
    desc: '审核方案与报告一致性、执行闭环性',
    tint: '#d9f3e1',
  },
]

export default function ValidationAuditNewClient() {
  const { message } = App.useApp()
  const router = useRouter()
  const [form] = Form.useForm()
  const [submitting, setSubmitting] = useState(false)
  const [fileList, setFileList] = useState<any[]>([])
  const [auditMode, setAuditMode] = useState<AuditMode>('protocol')

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()

      if (fileList.length === 0) {
        message.error('请上传至少一个审核文件')
        return
      }
      const MAX_BYTES = 50 * 1024 * 1024
      const oversized = fileList.find((f) => ((f.originFileObj || f) as File).size > MAX_BYTES)
      if (oversized) {
        message.error(`文件「${oversized.name}」超过 50MB 限制`)
        return
      }

      setSubmitting(true)

      const createResult = await createValidationAuditTask({
        task_name: values.task_name,
        product_name: values.product_name,
        method_name: values.method_name,
        source_company: values.source_company,
        audit_mode: values.audit_mode,
      })

      if (!createResult.success || !createResult.data) {
        message.error(createResult.message)
        setSubmitting(false)
        return
      }

      const taskId = createResult.data.id

      // 联合审核需要区分方案/报告两类文件；单文件组上传无法表达分类，
      // 引导到详情页分类型上传，避免报告被错误标记为方案。
      if (values.audit_mode === 'protocol_report') {
        message.info('联合审核模式：请进入任务详情，分别上传验证方案与验证报告')
        router.push(`/registration/validation-audit/${taskId}`)
        return
      }

      const formData = new FormData()
      for (const file of fileList) {
        const originFile = file.originFileObj || file
        formData.append('files', originFile)
      }
      formData.append('file_type', values.audit_mode)

      const uploadResult = await uploadValidationAuditFiles(taskId, formData)
      if (!uploadResult.success) {
        message.error(`文件上传失败: ${uploadResult.message}`)
        setSubmitting(false)
        return
      }

      message.success('任务创建成功，正在进入审核...')
      router.push(`/registration/validation-audit/${taskId}`)
    } catch (error) {
      if (error instanceof Error) {
        message.error(error.message)
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="w-full">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <Button
          type="text"
          icon={<ArrowLeftOutlined />}
          onClick={() => router.push('/registration/validation-audit')}
          style={{ borderRadius: 8 }}
        />
        <div>
          <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)] mb-0.5">
            新建验证审核任务
          </h1>
          <Text type="secondary" className="text-[13px]">
            填写基本信息、选择审核模式、上传待审核文件
          </Text>
        </div>
      </div>

      <Form form={form} layout="vertical" initialValues={{ audit_mode: 'protocol' }}>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left Column: Task Info */}
        <div className="space-y-6">
          {/* Audit Mode */}
          <Card
            style={{ borderRadius: 12, border: '1px solid var(--color-hairline)' }}
            styles={{ body: { padding: '24px' } }}
          >
            <div className="mb-4">
              <div className="flex items-center gap-2 mb-1">
                <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-[var(--color-primary)] text-white text-[11px] font-semibold">1</span>
                <span className="text-[15px] font-medium text-[var(--color-charcoal)]">选择审核模式</span>
              </div>
              <Text type="secondary" className="text-[12px] ml-7">
                根据审核范围选择对应模式
              </Text>
            </div>

            <div>
              <Form.Item name="audit_mode" noStyle>
                <Radio.Group
                  value={auditMode}
                  onChange={(e) => {
                    setAuditMode(e.target.value)
                    form.setFieldValue('audit_mode', e.target.value)
                  }}
                  className="w-full"
                >
                  <div className="grid grid-cols-3 gap-3">
                    {AUDIT_MODE_CARDS.map((card) => (
                      <Radio.Button
                        key={card.value}
                        value={card.value}
                        className="!h-auto !rounded-lg !border-[var(--color-hairline)] !py-4 !px-3 !text-left"
                        style={{
                          backgroundColor: auditMode === card.value ? card.tint : 'var(--color-surface-soft)',
                          borderColor: auditMode === card.value ? 'var(--color-primary)' : undefined,
                        }}
                      >
                        <div className="flex flex-col items-center text-center gap-2">
                          <div style={{ color: auditMode === card.value ? 'var(--color-primary)' : 'var(--color-steel)' }}>
                            {card.icon}
                          </div>
                          <div className="text-[13px] font-medium text-[var(--color-charcoal)]">
                            {card.title}
                          </div>
                          <div className="text-[11px] text-[var(--color-steel)] leading-snug">
                            {card.desc}
                          </div>
                        </div>
                      </Radio.Button>
                    ))}
                  </div>
                </Radio.Group>
              </Form.Item>
            </div>
          </Card>

          {/* Task Info Form */}
          <Card
            style={{ borderRadius: 12, border: '1px solid var(--color-hairline)' }}
            styles={{ body: { padding: '24px' } }}
          >
            <div className="mb-4">
              <div className="flex items-center gap-2 mb-1">
                <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-[var(--color-primary)] text-white text-[11px] font-semibold">2</span>
                <span className="text-[15px] font-medium text-[var(--color-charcoal)]">填写任务信息</span>
              </div>
            </div>

            <div>
              <Form.Item
                name="task_name"
                label={<span className="text-[13px] font-medium">任务名称</span>}
                rules={[{ required: true, message: '请输入任务名称' }]}
              >
                <Input placeholder="如：XX品种HPLC含量测定验证方案审核" maxLength={300} style={{ borderRadius: 8 }} />
              </Form.Item>

              <div className="grid grid-cols-2 gap-4">
                <Form.Item
                  name="product_name"
                  label={<span className="text-[13px] font-medium">品种名称</span>}
                  rules={[{ required: true, message: '请输入品种名称' }]}
                >
                  <Input placeholder="如：盐酸万古霉素" maxLength={200} style={{ borderRadius: 8 }} />
                </Form.Item>

                <Form.Item
                  name="method_name"
                  label={<span className="text-[13px] font-medium">方法名称</span>}
                  rules={[{ required: true, message: '请输入方法名称' }]}
                >
                  <Input placeholder="如：HPLC含量测定" maxLength={300} style={{ borderRadius: 8 }} />
                </Form.Item>
              </div>

              <Form.Item
                name="source_company"
                label={<span className="text-[13px] font-medium">来源公司</span>}
                rules={[{ required: true, message: '请输入来源公司' }]}
                className="mb-0"
              >
                <Input placeholder="文件提供方公司名称" maxLength={300} style={{ borderRadius: 8 }} />
              </Form.Item>
            </div>
          </Card>
        </div>

        {/* Right Column: File Upload */}
        <div className="space-y-6">
          <Card
            style={{ borderRadius: 12, border: '1px solid var(--color-hairline)' }}
            styles={{ body: { padding: '24px' } }}
            className="h-full"
          >
            <div className="mb-4">
              <div className="flex items-center gap-2 mb-1">
                <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-[var(--color-primary)] text-white text-[11px] font-semibold">3</span>
                <span className="text-[15px] font-medium text-[var(--color-charcoal)]">上传审核文件</span>
              </div>
              <Text type="secondary" className="text-[12px] ml-7">
                {auditMode === 'protocol_report'
                  ? '联合审核：创建任务后请在详情页分别上传验证方案与验证报告'
                  : auditMode === 'protocol' ? '请上传验证方案文件' : '请上传验证报告文件'}
              </Text>
            </div>

            <Dragger
              multiple
              accept=".docx,.pdf"
              fileList={fileList}
              beforeUpload={() => false}
              onChange={({ fileList: newList }) => setFileList(newList)}
              style={{
                borderRadius: 10,
                padding: '40px 0',
                backgroundColor: 'var(--color-surface-soft)',
                borderColor: 'var(--color-hairline)',
              }}
            >
              <p className="text-[48px] text-[var(--color-primary)] mb-3">
                <InboxOutlined />
              </p>
              <p className="text-[15px] text-[var(--color-charcoal)] mb-1 font-medium">
                点击或拖拽文件到此区域
              </p>
              <p className="text-[12px] text-[var(--color-stone)]">
                支持 DOCX、PDF 格式，单文件不超过 50MB
              </p>
            </Dragger>

            {fileList.length > 0 && (
              <div className="mt-4 space-y-2">
                <Text type="secondary" className="text-[12px] font-medium">已选择文件：</Text>
                {fileList.map((f, idx) => (
                  <div key={idx} className="flex items-center justify-between px-3 py-2 bg-[var(--color-surface)] rounded-lg text-[13px]">
                    <span className="text-[var(--color-charcoal)] truncate mr-2">
                      <FileTextOutlined className="mr-2 text-[var(--color-primary)]" />
                      {f.name}
                    </span>
                    <span className="text-[var(--color-stone)] shrink-0">
                      {(f.size / 1024 / 1024).toFixed(2)} MB
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      </div>
      </Form>

      {/* Actions */}
      <div className="flex justify-end gap-3 mt-6 pb-8">
        <Button
          size="large"
          onClick={() => router.push('/registration/validation-audit')}
          style={{ borderRadius: 8 }}
        >
          取消
        </Button>
        <Button
          type="primary"
          size="large"
          loading={submitting}
          onClick={handleSubmit}
          disabled={fileList.length === 0}
          icon={submitting ? undefined : <CheckCircleFilled />}
          style={{ borderRadius: 8, minWidth: 160 }}
        >
          {submitting ? '创建中...' : '创建并开始审核'}
        </Button>
      </div>
    </div>
  )
}
