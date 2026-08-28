'use client'

import { useState } from 'react'
import { Upload, Button, Card, Alert, Space, App, Typography } from 'antd'
import { UploadOutlined, RobotOutlined, FileTextOutlined } from '@ant-design/icons'
import type { UploadFile } from 'antd/es/upload/interface'
import { parseExperimentRecord, parseProcessParameters } from '@/actions/ai-parse'

const { Text } = Typography

export interface ParsedBatchData {
  batch_no?: string
  scale_g?: number
  scale_kg?: number
  date?: string
  operator?: string
  equipment?: string
  temperature?: string | number
  time?: string | number
  ratio?: string | number
  other_parameters?: string
  yield_pct?: number
  purity_pct?: number
  impurities_pct?: number
  appearance?: string
  observations?: string
  conclusion?: string
  comparison_notes?: string
}

interface AIFileParserProps {
  /** 解析类型 */
  parseType: 'lab_confirmation' | 'scale_up'
  /** 解析完成回调 */
  onParseComplete: (data: ParsedBatchData) => void
  /** 支持的文本内容解析（可选） */
  supportTextParse?: boolean
  /** 提示文本 */
  hint?: string
}

export function AIFileParser({ 
  parseType, 
  onParseComplete, 
  supportTextParse = true,
  hint 
}: AIFileParserProps) {
  const { message } = App.useApp()
  const [fileList, setFileList] = useState<UploadFile[]>([])
  const [parsing, setParsing] = useState(false)
  const [textContent, setTextContent] = useState('')
  const [showTextInput, setShowTextInput] = useState(false)

  const handleFileUpload = async (file: File) => {
    setParsing(true)
    try {
      const result = await parseExperimentRecord(file, parseType)
      message.success('文件解析完成，已自动填充表单')
      onParseComplete(result)
      return false // 阻止自动上传
    } catch (err) {
      message.error(err.message || '文件解析失败')
      return false
    } finally {
      setParsing(false)
    }
  }

  const handleTextParse = async () => {
    if (!textContent.trim()) {
      message.warning('请输入实验记录内容')
      return
    }

    setParsing(true)
    try {
      const result = await parseProcessParameters(textContent, parseType)
      message.success('内容解析完成，已自动填充表单')
      onParseComplete(result)
      setTextContent('')
      setShowTextInput(false)
    } catch (err) {
      message.error(err.message || '内容解析失败')
    } finally {
      setParsing(false)
    }
  }

  const defaultHint = parseType === 'lab_confirmation' 
    ? '支持上传实验记录、批记录、工艺规程等文件，AI将自动识别并填充表单'
    : '支持上传放大试验记录、批记录等文件，AI将自动识别并填充表单'

  return (
    <Card 
      size="small" 
      title={
        <Space>
          <RobotOutlined style={{ color: '#1890ff' }} />
          <span>AI智能识别</span>
        </Space>
      }
      style={{ marginBottom: 16, background: '#f6ffed', border: '1px solid #b7eb8f' }}
    >
      <Alert
        type="info"
        showIcon
        title="AI辅助填写"
        description={hint || defaultHint}
        style={{ marginBottom: 12 }}
      />

      <Space orientation="vertical" style={{ width: '100%' }} size="middle">
        {/* 文件上传 */}
        <div>
          <Text strong style={{ display: 'block', marginBottom: 8 }}>
            <FileTextOutlined /> 上传文件
          </Text>
          <Upload
            fileList={fileList}
            beforeUpload={handleFileUpload}
            onRemove={() => setFileList([])}
            maxCount={1}
            accept=".pdf,.doc,.docx,.txt,.jpg,.jpeg,.png"
            showUploadList={{ showPreviewIcon: false }}
          >
            <Button icon={<UploadOutlined />} loading={parsing} block>
              选择文件（PDF/Word/图片/文本）
            </Button>
          </Upload>
          <Text type="secondary" style={{ fontSize: 12, marginTop: 4, display: 'block' }}>
            支持格式：PDF、Word、TXT、JPG、PNG
          </Text>
        </div>

        {/* 文本输入 */}
        {supportTextParse && (
          <div>
            <Text strong style={{ display: 'block', marginBottom: 8 }}>
              <RobotOutlined /> 或粘贴实验记录
            </Text>
            {!showTextInput ? (
              <Button 
                type="dashed" 
                block 
                onClick={() => setShowTextInput(true)}
              >
                点击输入文本内容
              </Button>
            ) : (
              <Space orientation="vertical" style={{ width: '100%' }}>
                <textarea
                  value={textContent}
                  onChange={(e) => setTextContent(e.target.value)}
                  placeholder="粘贴实验记录、工艺参数等内容，AI将自动识别并提取关键信息..."
                  style={{
                    width: '100%',
                    minHeight: 120,
                    padding: 8,
                    border: '1px solid #d9d9d9',
                    borderRadius: 6,
                    fontFamily: 'monospace',
                    fontSize: 13,
                    resize: 'vertical'
                  }}
                />
                <Space>
                  <Button 
                    type="primary" 
                    onClick={handleTextParse}
                    loading={parsing}
                    disabled={!textContent.trim()}
                  >
                    <RobotOutlined /> AI识别并填充
                  </Button>
                  <Button onClick={() => {
                    setShowTextInput(false)
                    setTextContent('')
                  }}>
                    取消
                  </Button>
                </Space>
              </Space>
            )}
          </div>
        )}
      </Space>

      {parsing && (
        <Alert
          type="info"
          showIcon
          title="AI正在解析中..."
          description="请稍候，AI正在识别文件内容并提取关键信息"
          style={{ marginTop: 12 }}
        />
      )}
    </Card>
  )
}
