'use client'

import { useEffect, useState } from 'react'
import { App, AutoComplete, Button, Row, Col, Popconfirm, Spin, Modal, Form, Select, Upload, Input } from 'antd'
import { PlusOutlined, ImportOutlined, FileTextOutlined } from '@ant-design/icons'
import Link from 'next/link'
import { AnnualTrainingPlan } from '@/types/hr'
import { fetchAnnualTrainingPlans, fetchTrainingDepartments } from '@/lib/api/client/hr'
import { createAnnualTrainingPlan, deleteAnnualTrainingPlan, importAnnualTrainingPlan } from '@/actions/hr'
import { with201SubDepts } from './trainingDept'

// 年份选项：从去年到未来 5 年（自动跟随当前年份扩展），2025 年之前的年份不展示
const CURRENT_YEAR = new Date().getFullYear()
const YEAR_OPTIONS = Array.from({ length: 7 }, (_, i) => CURRENT_YEAR - 1 + i)

export default function AnnualPlanListClient() {
  const { message } = App.useApp()

  const [plans, setPlans] = useState<AnnualTrainingPlan[]>([])
  const [loading, setLoading] = useState(true)
  // 默认选中当前年份（此前硬编码 2026，跨年后默认筛选失效）
  const [selectedYear, setSelectedYear] = useState<number | undefined>(CURRENT_YEAR)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [form] = Form.useForm()
  const [departments, setDepartments] = useState<string[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [modalLoading, setModalLoading] = useState(false)
  const [importModalOpen, setImportModalOpen] = useState(false)
  const [importForm] = Form.useForm()
  const [importing, setImporting] = useState(false)
  const [importFile, setImportFile] = useState<File | null>(null)

  const loadPlans = async () => {
    setLoading(true)
    try {
      const res = await fetchAnnualTrainingPlans({
        year: selectedYear,
        page_size: 200
      })
      setPlans(res.data || [])
    } catch (err) {
      message.error('加载计划列表失败: ' + ((err instanceof Error ? err.message : '') || '未知错误'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    queueMicrotask(loadPlans)
  }, [selectedYear])

  const handleDelete = async (id: string) => {
    try {
      await deleteAnnualTrainingPlan(id)
      setPlans((prev) => prev.filter((p) => p.id !== id))
      message.success('删除成功')
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '删除失败')
    }
  }

  const openModal = () => {
    setIsModalOpen(true)
    setModalLoading(true)
    fetchTrainingDepartments()
      .then((depts) => {
        setDepartments(with201SubDepts(depts))
      })
      .catch(() => {
        message.error('加载部门列表失败')
      })
      .finally(() => setModalLoading(false))
  }

  const handleCreate = async (values: { year: number; department: string; plan_level: string }) => {
    setSubmitting(true)
    try {
      const res = await createAnnualTrainingPlan({
        year: values.year,
        department: values.department,
        plan_level: values.plan_level,
      })
      message.success('年度培训计划创建成功')
      setIsModalOpen(false)
      form.resetFields()
      const planId = res.data?.id
      if (planId) {
        window.location.href = `/hr/training/annual-plan?id=${planId}`
      } else {
        loadPlans()
      }
    } catch (err) {
      const msg = (err instanceof Error ? err.message : '') || ''
      if (msg.includes('已存在') || msg.includes('Duplicate')) {
        message.error('该部门年度培训计划已存在')
      } else {
        message.error(msg || '创建失败')
      }
    } finally {
      setSubmitting(false)
    }
  }

  const handleImport = async () => {
    try {
      const values = await importForm.validateFields()
      if (!importFile) {
        message.error('请选择Word文档')
        return
      }
      setImporting(true)
      const res = await importAnnualTrainingPlan(
        importFile,
        values.year
      )
      message.success(res.message || '导入成功')
      setImportModalOpen(false)
      importForm.resetFields()
      setImportFile(null)
      loadPlans()
    } catch (err) {
      if ((typeof err === 'object' && err !== null && 'errorFields' in err)) return // 表单校验错误
      message.error((err instanceof Error ? err.message : '') || '导入失败')
    } finally {
      setImporting(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* 顶部筛选与新建 */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="text-sm text-[var(--color-steel)]">年份：</span>
          <Select
            style={{ width: 120 }}
            value={selectedYear}
            onChange={(val) => setSelectedYear(val)}
            options={YEAR_OPTIONS.map((y) => ({ label: `${y}年`, value: y }))}
            allowClear
            placeholder="全部年份"
          />
        </div>
        <div className="flex gap-2">
          <Button icon={<ImportOutlined />} onClick={() => setImportModalOpen(true)}>
            导入文档
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openModal}>
            新建年度计划
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <Spin size="large" description="加载中..." />
        </div>
      ) : plans.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-gray-400">
          <FileTextOutlined className="text-5xl mb-4" />
          <p>
            {selectedYear ? `${selectedYear}年暂无年度培训计划` : '暂无年度培训计划'}
          </p>
          <p className="text-sm mt-2">点击上方按钮新建</p>
        </div>
      ) : (
        <>
          {/* 公司级计划 */}
          {plans.filter((p) => p.plan_level === '公司级').length > 0 && (
            <div className="mb-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-1 h-[22px] rounded-full bg-blue-500" />
                <h2 className="text-[16px] font-semibold text-[var(--color-charcoal)] m-0">
                  公司级
                </h2>
                <span className="text-[12px] text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">
                  全局培训计划
                </span>
              </div>
              <Row gutter={[16, 16]}>
                {plans
                  .filter((p) => p.plan_level === '公司级')
                  .map((plan) => (
                    <Col xs={24} sm={12} md={8} lg={6} key={plan.id}>
                      <div className="group relative rounded-xl border border-blue-100 bg-gradient-to-br from-blue-50/60 to-white p-4 shadow-sm hover:shadow-md hover:border-blue-300 transition-all duration-300 cursor-pointer"
                           onClick={(e) => {
                             // 只在点击卡片内部时跳转；Popconfirm 确认浮层在卡片 DOM 外，点击确定不会误跳转
                             if (!e.currentTarget.contains(e.target as Node)) return
                             window.location.href = `/hr/training/annual-plan?id=${plan.id}`
                           }}>
                        <div className="flex items-start gap-3 mb-3">
                          <div className="w-9 h-9 rounded-lg bg-blue-500 flex items-center justify-center flex-shrink-0">
                            <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9a2 2 0 00-2-2h-2m-4-3H9M7 16h6M7 8h6v4H7V8z" />
                            </svg>
                          </div>
                          <div className="min-w-0">
                            <div className="text-[14px] font-semibold text-[var(--color-charcoal)] truncate">
                              {plan.department}
                            </div>
                            <div className="text-[12px] text-[var(--color-steel)] mt-0.5">
                              {plan.year} 年度培训计划
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-1 pt-3 border-t border-blue-100">
                          <Link
                            href={`/hr/training/annual-plan?id=${plan.id}`}
                            className="flex-1 text-center text-[12px] text-blue-600 hover:text-blue-700 hover:bg-blue-50 rounded-md py-1 transition-colors"
                            onClick={(e) => e.stopPropagation()}
                          >
                            查看
                          </Link>
                          <span className="text-gray-200">|</span>
                          <Popconfirm
                            title="确认删除该年度培训计划？"
                            onConfirm={() => handleDelete(plan.id)}
                          >
                            <span
                              className="flex-1 text-center text-[12px] text-red-500 hover:text-red-600 hover:bg-red-50 rounded-md py-1 cursor-pointer transition-colors"
                              onClick={(e) => e.stopPropagation()}
                            >
                              删除
                            </span>
                          </Popconfirm>
                        </div>
                      </div>
                    </Col>
                  ))}
              </Row>
            </div>
          )}

          {/* 部门级计划 */}
          {plans.filter((p) => p.plan_level !== '公司级').length > 0 && (
            <div>
              <div className="flex items-center gap-3 mb-4">
                <div className="w-1 h-[22px] rounded-full bg-emerald-500" />
                <h2 className="text-[16px] font-semibold text-[var(--color-charcoal)] m-0">
                  部门级
                </h2>
                <span className="text-[12px] text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">
                  {plans.filter((p) => p.plan_level !== '公司级').length} 个部门
                </span>
              </div>
              <Row gutter={[16, 16]}>
                {plans
                  .filter((p) => p.plan_level !== '公司级')
                  .map((plan) => (
                    <Col xs={24} sm={12} md={8} lg={6} key={plan.id}>
                      <div className="group relative rounded-xl border border-gray-100 bg-white p-4 shadow-sm hover:shadow-md hover:border-emerald-200 transition-all duration-300 cursor-pointer"
                           onClick={(e) => {
                             // 只在点击卡片内部时跳转；Popconfirm 确认浮层在卡片 DOM 外，点击确定不会误跳转
                             if (!e.currentTarget.contains(e.target as Node)) return
                             window.location.href = `/hr/training/annual-plan?id=${plan.id}`
                           }}>
                        <div className="flex items-start gap-3 mb-3">
                          <div className="w-9 h-9 rounded-lg bg-emerald-500 flex items-center justify-center flex-shrink-0">
                            <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                            </svg>
                          </div>
                          <div className="min-w-0">
                            <div className="text-[14px] font-semibold text-[var(--color-charcoal)] truncate">
                              {plan.department}
                            </div>
                            <div className="text-[12px] text-[var(--color-steel)] mt-0.5">
                              {plan.year} 年度培训计划
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-1 pt-3 border-t border-gray-100">
                          <Link
                            href={`/hr/training/annual-plan?id=${plan.id}`}
                            className="flex-1 text-center text-[12px] text-emerald-600 hover:text-emerald-700 hover:bg-emerald-50 rounded-md py-1 transition-colors"
                            onClick={(e) => e.stopPropagation()}
                          >
                            查看
                          </Link>
                          <span className="text-gray-200">|</span>
                          <Popconfirm
                            title="确认删除该年度培训计划？"
                            onConfirm={() => handleDelete(plan.id)}
                          >
                            <span
                              className="flex-1 text-center text-[12px] text-red-500 hover:text-red-600 hover:bg-red-50 rounded-md py-1 cursor-pointer transition-colors"
                              onClick={(e) => e.stopPropagation()}
                            >
                              删除
                            </span>
                          </Popconfirm>
                        </div>
                      </div>
                    </Col>
                  ))}
              </Row>
            </div>
          )}
        </>
      )}

      {/* 新建模态框 */}
      <Modal
        title="新建年度培训计划"
        open={isModalOpen}
        onCancel={() => {
          setIsModalOpen(false)
          form.resetFields()
        }}
        footer={null}
        destroyOnHidden
      >
        <Spin spinning={modalLoading} description="加载部门列表...">
          <Form
            form={form}
            layout="vertical"
            onFinish={handleCreate}
            initialValues={{ year: new Date().getFullYear(), plan_level: '公司级' }}
            className="mt-4"
          >
            <Form.Item
              label="年度"
              name="year"
              rules={[{ required: true, message: '请选择年度' }]}
            >
              <Select
                options={YEAR_OPTIONS.map((y) => ({ label: `${y}年`, value: y }))}
                placeholder="选择年度"
              />
            </Form.Item>

            <Form.Item
              label="计划级别"
              name="plan_level"
              rules={[{ required: true, message: '请选择计划级别' }]}
            >
              <Select
                options={[
                  { label: '公司级', value: '公司级' },
                  { label: '部门级', value: '部门级' },
                ]}
                placeholder="选择计划级别"
                onChange={(value: string) => {
                  if (value === '公司级') {
                    form.setFieldValue('department', '公司')
                  } else {
                    form.setFieldValue('department', undefined)
                  }
                }}
              />
            </Form.Item>

            <Form.Item noStyle shouldUpdate={(prev, cur) => prev.plan_level !== cur.plan_level}>
              {({ getFieldValue }) =>
                getFieldValue('plan_level') === '部门级' ? (
                  <Form.Item
                    label="部门"
                    name="department"
                    rules={[{ required: true, message: '请选择部门' }]}
                  >
                    <AutoComplete
                      options={departments.map((d) => ({ value: d }))}
                      placeholder="选择或输入部门"
                      filterOption={(input, option) =>
                        (option?.value ?? '').toLowerCase().includes(input.toLowerCase())
                      }
                    />
                  </Form.Item>
                ) : (
                  <Form.Item label="部门">
                    <Input disabled value="公司" />
                    <Form.Item name="department" hidden initialValue="公司">
                      <Input />
                    </Form.Item>
                  </Form.Item>
                )
              }
            </Form.Item>

            <Form.Item className="mb-0 flex justify-end gap-2">
              <Button onClick={() => setIsModalOpen(false)}>取消</Button>
              <Button type="primary" htmlType="submit" loading={submitting}>
                创建
              </Button>
            </Form.Item>
          </Form>
        </Spin>
      </Modal>

      <Modal
        title="导入年度培训计划"
        open={importModalOpen}
        onOk={handleImport}
        onCancel={() => { setImportModalOpen(false); setImportFile(null) }}
        confirmLoading={importing}
        destroyOnHidden
      >
        <Form
          form={importForm}
          layout="vertical"
          initialValues={{ year: new Date().getFullYear() }}
          className="mt-4"
        >
          <Form.Item label="年度" name="year" rules={[{ required: true }]}>
            <Select
              options={YEAR_OPTIONS.map((y) => ({ label: `${y}年`, value: y }))}
              placeholder="选择年度"
            />
          </Form.Item>
          <Form.Item label="Word文档" required>
            <Upload
              accept=".docx"
              maxCount={1}
              beforeUpload={(file) => {
                setImportFile(file)
                return false // 阻止自动上传
              }}
              onRemove={() => setImportFile(null)}
              fileList={importFile ? [{ uid: '-1', name: importFile.name, status: 'done' }] : []}
            >
              <Button>选择文档</Button>
            </Upload>
            <p className="text-xs text-gray-400 mt-1">
              支持 APP1（年度部门培训计划表）/ APP2（年度公司培训计划表）格式，系统自动识别文档中的计划级别和部门，并归入对应部门的培训计划
            </p>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
