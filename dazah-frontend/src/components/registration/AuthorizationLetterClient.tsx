'use client'

import { useState, useCallback, useEffect } from 'react'
import { Table, Input, Select, Button, Space, App, Card, Modal, Form, Upload, InputNumber } from 'antd'
import { PlusOutlined, UploadOutlined, DownloadOutlined, DeleteOutlined } from '@ant-design/icons'
import { AuthorizationLetterListItem, ProductInfo } from '@/types/registration'
import { fetchAuthorizationLetters, getAuthorizationLetterDownloadUrl } from '@/lib/api/registration'
import { generateAuthorizationLetter, deleteAuthorizationLetter } from '@/actions/registration'
import dayjs from 'dayjs'

const { Option } = Select

interface AuthorizationLetterClientProps {
  initialLetters: AuthorizationLetterListItem[]
  initialTotal: number
  products: ProductInfo[]
}

export default function AuthorizationLetterClient({
  initialLetters,
  initialTotal,
  products,
}: AuthorizationLetterClientProps) {
  const { message, modal } = App.useApp()
  const [letters, setLetters] = useState<AuthorizationLetterListItem[]>(initialLetters)
  const [total, setTotal] = useState(initialTotal)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [loading, setLoading] = useState(false)
  const [productName, setProductName] = useState('')
  const [preparationUnit, setPreparationUnit] = useState('')
  const [generateModalOpen, setGenerateModalOpen] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [form] = Form.useForm()
  const [fileList, setFileList] = useState<any[]>([])
  const [replacements, setReplacements] = useState<Array<{old: string, new: string}>>([
    {old: '', new: ''},
  ])

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetchAuthorizationLetters({
        product_name: productName || undefined,
        preparation_unit: preparationUnit || undefined,
        page,
        page_size: pageSize,
      })
      setLetters(res.data)
      setTotal(res.meta?.total || 0)
    } catch (err: any) {
      message.error(err.message || '加载数据失败')
    } finally {
      setLoading(false)
    }
  }, [productName, preparationUnit, page, pageSize])

  useEffect(() => {
    loadData()
  }, [loadData])

  const handlePageChange = (newPage: number, newPageSize: number) => {
    setPage(newPage)
    setPageSize(newPageSize)
  }

  const handleProductChange = (value: string) => {
    form.setFieldsValue({
      product_name: value,
      registration_number: products.find(p => p.product_name === value)?.registration_number || '',
    })
  }

  const addReplacement = () => {
    setReplacements([...replacements, {old: '', new: ''}])
  }

  const autoFillReplacements = () => {
    const values = form.getFieldsValue()
    if (!values.product_name || !values.preparation_unit) {
      message.warning('请先填写产品名称和制剂单位')
      return
    }
    
    // 基于常见模板格式的替换规则
    const autoRules = [
      {old: '海口市制药厂有限公司', new: values.preparation_unit},
      {old: '注射用头孢曲松钠', new: values.preparation_name},
      {old: '头孢曲松钠', new: values.product_name},
      {old: 'Y20190009444', new: values.registration_number},
    ]
    
    setReplacements(autoRules)
    message.success('已自动填充替换规则，请检查字符数是否匹配')
  }

  const removeReplacement = (index: number) => {
    setReplacements(replacements.filter((_, i) => i !== index))
  }

  const updateReplacement = (index: number, field: 'old' | 'new', value: string) => {
    const newReplacements = [...replacements]
    newReplacements[index][field] = value
    setReplacements(newReplacements)
  }

  const handleGenerate = async () => {
    try {
      const values = await form.validateFields()
      
      if (fileList.length === 0) {
        message.error('请上传模板文件')
        return
      }

      setGenerating(true)
      
      const formData = new FormData()
      formData.append('template', fileList[0].originFileObj)
      
      // 添加替换规则
      const validReplacements = replacements.filter(r => r.old && r.new)
      if (validReplacements.length > 0) {
        formData.append('replacements', JSON.stringify(validReplacements))
      }
      
      const result = await generateAuthorizationLetter(formData, {
        product_name: values.product_name,
        registration_number: values.registration_number,
        preparation_unit: values.preparation_unit,
        preparation_name: values.preparation_name,
        administration_route: values.administration_route,
        remarks: values.remarks,
      })

      if (result.success) {
        message.success(result.message)
        setGenerateModalOpen(false)
        form.resetFields()
        setFileList([])
        loadData()
      } else {
        message.error(result.message)
      }
    } catch (err: any) {
      message.error(err.message || '生成失败')
    } finally {
      setGenerating(false)
    }
  }

  const handleDelete = async (id: string) => {
    modal.confirm({
      title: '确认删除',
      content: '确定要删除这条授权书记录吗？',
      onOk: async () => {
        try {
          await deleteAuthorizationLetter(id)
          message.success('删除成功')
          loadData()
        } catch (err: any) {
          message.error(err.message || '删除失败')
        }
      },
    })
  }

  const handleDownload = async (id: string, fileName: string) => {
    const url = await getAuthorizationLetterDownloadUrl(id)
    const link = document.createElement('a')
    link.href = url
    link.download = fileName
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  const columns = [
    {
      title: '产品名称',
      dataIndex: 'product_name',
      key: 'product_name',
      width: 150,
    },
    {
      title: '登记号',
      dataIndex: 'registration_number',
      key: 'registration_number',
      width: 140,
    },
    {
      title: '制剂单位',
      dataIndex: 'preparation_unit',
      key: 'preparation_unit',
      width: 200,
    },
    {
      title: '制剂名称',
      dataIndex: 'preparation_name',
      key: 'preparation_name',
      width: 180,
    },
    {
      title: '给药途径',
      dataIndex: 'administration_route',
      key: 'administration_route',
      width: 100,
    },
    {
      title: '生成时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (time: string) => dayjs(time).format('YYYY-MM-DD HH:mm'),
    },
    {
      title: '操作',
      key: 'action',
      width: 150,
      fixed: 'right' as const,
      render: (_: any, record: AuthorizationLetterListItem) => (
        <Space>
          <Button
            type="link"
            size="small"
            icon={<DownloadOutlined />}
            onClick={() => handleDownload(record.id, record.output_file_name)}
          >
            下载
          </Button>
          <Button
            type="link"
            size="small"
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
      <Card className="mb-4">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold">授权书管理</h2>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setGenerateModalOpen(true)}
          >
            生成授权书
          </Button>
        </div>

        <div className="flex gap-4 mb-4">
          <Input
            placeholder="产品名称"
            value={productName}
            onChange={(e) => setProductName(e.target.value)}
            style={{ width: 200 }}
            allowClear
          />
          <Input
            placeholder="制剂单位"
            value={preparationUnit}
            onChange={(e) => setPreparationUnit(e.target.value)}
            style={{ width: 200 }}
            allowClear
          />
          <Button onClick={() => { setPage(1); loadData() }}>搜索</Button>
        </div>

        <Table
          columns={columns}
          dataSource={letters}
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
        title="生成授权书"
        open={generateModalOpen}
        onOk={handleGenerate}
        onCancel={() => {
          setGenerateModalOpen(false)
          form.resetFields()
          setFileList([])
        }}
        confirmLoading={generating}
        width={600}
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="product_name"
            label="产品名称"
            rules={[{ required: true, message: '请选择产品名称' }]}
          >
            <Select
              placeholder="请选择产品"
              showSearch
              onChange={handleProductChange}
            >
              {products.map((product) => (
                <Option key={product.product_name} value={product.product_name}>
                  {product.product_name}
                </Option>
              ))}
            </Select>
          </Form.Item>

          <Form.Item
            name="registration_number"
            label="登记号"
            rules={[{ required: true, message: '请输入登记号' }]}
          >
            <Input placeholder="选择产品后自动填充" disabled />
          </Form.Item>

          <Form.Item
            name="preparation_unit"
            label="制剂单位名称"
            rules={[{ required: true, message: '请输入制剂单位名称' }]}
          >
            <Input placeholder="如：国药集团致君（深圳）制药有限公司" />
          </Form.Item>

          <Form.Item
            name="preparation_name"
            label="制剂名称"
            rules={[{ required: true, message: '请输入制剂名称' }]}
          >
            <Input placeholder="如：注射用头孢他啶" />
          </Form.Item>

          <Form.Item
            name="administration_route"
            label="给药途径"
            rules={[{ required: true, message: '请输入给药途径' }]}
          >
            <Input placeholder="如：注射" />
          </Form.Item>

          <Form.Item
            name="template"
            label="模板文件"
            rules={[{ required: true, message: '请上传模板文件' }]}
          >
            <Upload
              beforeUpload={() => false}
              fileList={fileList}
              onChange={({ fileList }) => setFileList(fileList)}
              maxCount={1}
              accept=".docx"
            >
              <Button icon={<UploadOutlined />}>选择 .docx 模板文件</Button>
            </Upload>
          </Form.Item>

          <Form.Item label="替换规则">
            <div className="space-y-2">
              {replacements.map((item, index) => (
                <div key={index} className="flex gap-2 items-center">
                  <Input
                    placeholder="原文本"
                    value={item.old}
                    onChange={(e) => updateReplacement(index, 'old', e.target.value)}
                    style={{ flex: 1 }}
                  />
                  <span>→</span>
                  <Input
                    placeholder="新文本"
                    value={item.new}
                    onChange={(e) => updateReplacement(index, 'new', e.target.value)}
                    style={{ flex: 1 }}
                  />
                  {replacements.length > 1 && (
                    <Button
                      type="text"
                      danger
                      onClick={() => removeReplacement(index)}
                      size="small"
                    >
                      删除
                    </Button>
                  )}
                </div>
              ))}
              <div className="flex gap-2">
                <Button type="dashed" onClick={addReplacement} style={{ flex: 1 }}>
                  + 添加替换规则
                </Button>
                <Button type="primary" onClick={autoFillReplacements}>
                  自动填充
                </Button>
              </div>
              <div className="text-xs text-gray-500">
                提示：原文本和新文本的字符数必须相同（中文字符算1个）
              </div>
            </div>
          </Form.Item>

          <Form.Item name="remarks" label="备注">
            <Input.TextArea rows={3} placeholder="可选" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
