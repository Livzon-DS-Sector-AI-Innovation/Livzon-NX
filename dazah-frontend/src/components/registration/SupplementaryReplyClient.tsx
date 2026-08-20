'use client'

import { useState, useCallback, useEffect } from 'react'
import { Table, Input, Button, Space, App, Card, Modal, Form, Upload } from 'antd'
import { UploadOutlined, DownloadOutlined, DeleteOutlined } from '@ant-design/icons'
import { SupplementaryReplyListItem } from '@/types/registration'
import { fetchSupplementaryReplies, getSupplementaryReplyDownloadUrl } from '@/lib/api/registration'
import { generateSupplementaryReply, deleteSupplementaryReplyAction } from '@/actions/registration'
import dayjs from 'dayjs'

interface SupplementaryReplyClientProps {
  initialReplies: SupplementaryReplyListItem[]
  initialTotal: number
}

export default function SupplementaryReplyClient({
  initialReplies,
  initialTotal,
}: SupplementaryReplyClientProps) {
  const { message } = App.useApp()
  const [replies, setReplies] = useState<SupplementaryReplyListItem[]>(initialReplies)
  const [total, setTotal] = useState(initialTotal)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [loading, setLoading] = useState(false)
  const [drugName, setDrugName] = useState('')
  const [generateModalOpen, setGenerateModalOpen] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [form] = Form.useForm()
  const [noticeFileList, setNoticeFileList] = useState<any[]>([])
  const [templateFileList, setTemplateFileList] = useState<any[]>([])

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetchSupplementaryReplies({
        drug_name: drugName || undefined,
        page,
        page_size: pageSize,
      })
      setReplies(res.data)
      setTotal(res.meta?.total || 0)
    } catch (err) {
      message.error(err.message || '加载数据失败')
    } finally {
      setLoading(false)
    }
  }, [drugName, page, pageSize])

  useEffect(() => {
    loadData()
  }, [loadData])

  const handlePageChange = (newPage: number, newPageSize: number) => {
    setPage(newPage)
    setPageSize(newPageSize)
  }

  const handleGenerate = async () => {
    try {
      const values = await form.validateFields()
      
      if (noticeFileList.length === 0) {
        message.error('请上传CDE通知函PDF')
        return
      }

      setGenerating(true)
      
      const formData = new FormData()
      formData.append('notice', noticeFileList[0].originFileObj)
      
      if (templateFileList.length > 0) {
        formData.append('template', templateFileList[0].originFileObj)
      }
      
      const result = await generateSupplementaryReply(formData, {
        drug_name: values.drug_name,
        registration_number: values.registration_number,
        acceptance_number: values.acceptance_number,
        company_name: values.company_name,
        remarks: values.remarks,
      })

      if (result.success) {
        message.success(result.message)
        setGenerateModalOpen(false)
        form.resetFields()
        setNoticeFileList([])
        setTemplateFileList([])
        loadData()
      } else {
        message.error(result.message)
      }
    } catch (err) {
      message.error(err.message || '生成失败')
    } finally {
      setGenerating(false)
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await deleteSupplementaryReplyAction(id)
      message.success('删除成功')
      loadData()
    } catch (err) {
      message.error(err.message || '删除失败')
    }
  }

  const columns = [
    {
      title: '药品名称',
      dataIndex: 'drug_name',
      key: 'drug_name',
      width: 200,
    },
    {
      title: '登记号',
      dataIndex: 'registration_number',
      key: 'registration_number',
      width: 150,
    },
    {
      title: '受理号',
      dataIndex: 'acceptance_number',
      key: 'acceptance_number',
      width: 150,
    },
    {
      title: '问题数量',
      dataIndex: 'question_count',
      key: 'question_count',
      width: 100,
    },
    {
      title: '生成文件',
      dataIndex: 'output_file_name',
      key: 'output_file_name',
      width: 250,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (text: string) => dayjs(text).format('YYYY-MM-DD HH:mm'),
    },
    {
      title: '操作',
      key: 'action',
      width: 150,
      fixed: 'right' as const,
      render: (_: any, record: SupplementaryReplyListItem) => (
        <Space>
          <Button
            type="link"
            icon={<DownloadOutlined />}
            onClick={async () => { const url = await getSupplementaryReplyDownloadUrl(record.id); window.open(url, "_blank"); }}
            target="_blank"
          >
            下载
          </Button>
          <Button
            type="link"
            danger
            icon={<DeleteOutlined />}
            onClick={() => handleDelete(record.id)}
          >
            删除
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)] mb-2">
        发补回复管理
      </h1>
      <p className="text-[14px] text-[var(--color-steel)] mb-4">
        根据CDE补充资料通知函自动生成发补回复Word文档
      </p>

      <Card>
        <div className="flex gap-4 mb-4">
          <Input
            placeholder="药品名称搜索"
            value={drugName}
            onChange={(e) => setDrugName(e.target.value)}
            style={{ width: 200 }}
            allowClear
          />
          <Button onClick={() => { setPage(1); loadData() }}>搜索</Button>
          <Button type="primary" onClick={() => setGenerateModalOpen(true)}>
            生成发补回复
          </Button>
        </div>

        <Table
          columns={columns}
          dataSource={replies}
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

      <Modal
        title="生成发补回复文档"
        open={generateModalOpen}
        onOk={handleGenerate}
        onCancel={() => {
          setGenerateModalOpen(false)
          form.resetFields()
          setNoticeFileList([])
          setTemplateFileList([])
        }}
        confirmLoading={generating}
        width={600}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="notice"
            label="CDE通知函（PDF）"
            rules={[{ required: true, message: '请上传CDE通知函PDF' }]}
          >
            <Upload
              beforeUpload={() => false}
              fileList={noticeFileList}
              onChange={({ fileList }) => setNoticeFileList(fileList)}
              maxCount={1}
              accept=".pdf"
            >
              <Button icon={<UploadOutlined />}>选择 PDF 文件</Button>
            </Upload>
          </Form.Item>

          <Form.Item
            name="template"
            label="公司模板（Word，可选）"
          >
            <Upload
              beforeUpload={() => false}
              fileList={templateFileList}
              onChange={({ fileList }) => setTemplateFileList(fileList)}
              maxCount={1}
              accept=".docx,.doc"
            >
              <Button icon={<UploadOutlined />}>选择 Word 文件（可选）</Button>
            </Upload>
          </Form.Item>

          <Form.Item
            name="drug_name"
            label="药品名称（可选，默认从PDF提取）"
          >
            <Input placeholder="如不填则自动从PDF提取" />
          </Form.Item>

          <Form.Item
            name="registration_number"
            label="登记号（可选）"
          >
            <Input placeholder="如不填则自动从PDF提取" />
          </Form.Item>

          <Form.Item
            name="acceptance_number"
            label="受理号（可选）"
          >
            <Input placeholder="如不填则自动从PDF提取" />
          </Form.Item>

          <Form.Item
            name="company_name"
            label="申请人/公司名称（可选）"
          >
            <Input placeholder="如不填则自动从PDF提取" />
          </Form.Item>

          <Form.Item name="remarks" label="备注">
            <Input.TextArea rows={3} placeholder="可选" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
