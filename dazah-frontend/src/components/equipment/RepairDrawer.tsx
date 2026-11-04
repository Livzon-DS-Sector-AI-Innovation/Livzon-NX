'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { App, Drawer, Form, Input, Select, Button, Space, Upload } from 'antd'
import { PlusOutlined, BookOutlined } from '@ant-design/icons'
import type { UploadFile } from 'antd/es/upload'
import { useEquipmentStore } from '@/stores/equipment'
import { createWorkOrder, uploadWorkOrderImages } from '@/actions/equipment'
import { CreateWorkOrderInput, FailureCode, Maintainer, KnowledgeCaseHit } from '@/types/equipment'
import { fetchAllUsersClient, searchKnowledgeCasesClient } from '@/lib/api/equipment-client'

const { TextArea } = Input

interface RepairDrawerProps {
  equipments: { id: string; equipment_no: string; name: string; importance?: string; responsible_person_id?: string | null }[]
  symptoms?: FailureCode[]
  onRefresh?: () => void
}

export function RepairDrawer({ equipments, symptoms, onRefresh }: RepairDrawerProps) {
  const { message } = App.useApp()
  const [form] = Form.useForm()
  const [fileList, setFileList] = useState<UploadFile[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [maintainers, setMaintainers] = useState<Maintainer[]>([])
  const [similarCases, setSimilarCases] = useState<KnowledgeCaseHit[]>([])
  const similarTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const { repairDrawerOpen, repairEquipmentId, closeRepairDrawer } = useEquipmentStore()

  const selectedEquipment = equipments.find(e => e.id === repairEquipmentId)

  // 相似案例是辅助信息：所有 setState 都在首个 await 之后（避免 effect 内
  // 同步 setState），检索失败静默返回空列表，不打断报修主流程
  const searchSimilar = useCallback(
    async (q: string) => {
      const query = q.trim()
      const equipmentId = repairEquipmentId
      const hits = await (async () => {
        if (!equipmentId || query.length < 2) return []
        try {
          return await searchKnowledgeCasesClient({
            q: query,
            equipment_id: equipmentId,
            top: 3,
          })
        } catch {
          return []
        }
      })()
      setSimilarCases(hits)
    },
    [repairEquipmentId],
  )

  useEffect(() => {
    if (repairDrawerOpen) {
      form.resetFields()
      const defaultPriority = selectedEquipment?.importance ?? '中'
      form.setFieldsValue({
        equipment_id: repairEquipmentId,
        order_type: '故障维修',
        priority: defaultPriority,
      })
      setFileList([])
      fetchAllUsersClient().then(setMaintainers).catch(() => {})
      // 打开时先按设备名检索一次该设备的过往案例
      if (selectedEquipment?.name) {
        void searchSimilar(selectedEquipment.name)
      }
      // 默认填入设备责任人
      if (selectedEquipment?.responsible_person_id) {
        form.setFieldsValue({ responsible_person_id: selectedEquipment.responsible_person_id })
      }
    }
  }, [repairDrawerOpen, repairEquipmentId, form, selectedEquipment, searchSimilar])

  // 故障描述输入变化时防抖检索相似案例
  const handleDescriptionChange = (e: { target: { value: string } }) => {
    const value = e.target.value
    if (similarTimer.current) clearTimeout(similarTimer.current)
    similarTimer.current = setTimeout(() => searchSimilar(value), 500)
  }

  useEffect(() => {
    return () => {
      if (similarTimer.current) clearTimeout(similarTimer.current)
    }
  }, [])

  const handleSubmit = async () => {
    try {
      setSubmitting(true)
      const values = await form.validateFields()
      const data: CreateWorkOrderInput = {
        equipment_id: repairEquipmentId!,
        order_type: '故障维修',
        priority: values.priority,
        fault_symptom_id: values.fault_symptom_id || undefined,
        fault_description: values.fault_description || undefined,
        responsible_person_id: values.responsible_person_id,
      }
      const result = await createWorkOrder(data)
      const workOrderId = (result as { id?: string } | null)?.id

      if (!workOrderId) {
        message.error('工单创建失败，请稍后重试')
        return
      }

      if (fileList.length > 0) {
        const formData = new FormData()
        fileList.forEach((file) => {
          if (file.originFileObj) {
            formData.append('files', file.originFileObj)
          }
        })
        await uploadWorkOrderImages(workOrderId, formData)
      }

      message.success('报修工单已提交')
      closeRepairDrawer()
      onRefresh?.()
    } catch (error) {
      if (error?.message) message.error(error.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Drawer
      title="报故障维修"
      size={480}
      open={repairDrawerOpen}
      onClose={closeRepairDrawer}
      destroyOnHidden
      extra={
        <Space>
          <Button onClick={closeRepairDrawer}>取消</Button>
          <Button type="primary" loading={submitting} onClick={handleSubmit}>
            提交工单
          </Button>
        </Space>
      }
    >
      <Form form={form} layout="vertical" requiredMark="optional" preserve={false}>
        <Form.Item name="equipment_id" label="关联设备">
          <div style={{ padding: '8px 12px', background: 'var(--color-surface)', borderRadius: 6, fontSize: 14, color: 'var(--color-charcoal)' }}>
            {selectedEquipment ? `${selectedEquipment.equipment_no} - ${selectedEquipment.name}` : '-'}
          </div>
        </Form.Item>
        <Form.Item name="order_type" label="工单类型">
          <div style={{ padding: '8px 12px', background: 'var(--color-surface)', borderRadius: 6, fontSize: 14, color: '#dd5b00', fontWeight: 500 }}>
            故障维修
          </div>
        </Form.Item>
        <Form.Item name="priority" label="优先级" rules={[{ required: true }]}>
          <Select
            options={[
              { label: '紧急', value: '紧急' },
              { label: '高', value: '高' },
              { label: '中', value: '中' },
              { label: '低', value: '低' },
            ]}
          />
        </Form.Item>
        <Form.Item name="fault_symptom_id" label="故障现象">
          <Select
            placeholder="选择故障现象（可选）"
            allowClear
            showSearch
            optionFilterProp="label"
            options={(symptoms || []).map((s) => ({ label: `${s.code} - ${s.name}`, value: s.id }))}
          />
        </Form.Item>
        <Form.Item name="fault_description" label="故障描述">
          <TextArea
            placeholder="请描述故障情况"
            rows={4}
            maxLength={500}
            showCount
            onChange={handleDescriptionChange}
          />
        </Form.Item>
        {similarCases.length > 0 && (
          <div
            style={{
              marginBottom: 16,
              padding: '10px 12px',
              background: 'var(--color-surface)',
              borderRadius: 6,
              fontSize: 12,
            }}
            data-testid="similar-cases-panel"
          >
            <div style={{ fontWeight: 600, marginBottom: 6 }}>
              <BookOutlined /> 相似历史案例（供参考）
            </div>
            {similarCases.map((c) => (
              <div key={c.id} style={{ padding: '4px 0', borderBottom: '1px dashed var(--color-border, #e5e3df)' }}>
                <div>
                  <span style={{ color: '#5d5b54' }}>
                    {c.symptom_name || '未记录现象'} → {c.cause_name || '未记录原因'} →{' '}
                    <span style={{ color: '#1f7a4d' }}>{c.action_name || '未记录措施'}</span>
                  </span>
                  {c.use_count > 0 && (
                    <span style={{ color: '#8a867d', marginLeft: 8 }}>被参考 {c.use_count} 次</span>
                  )}
                </div>
                {c.repair_summary && (
                  <div style={{ color: '#8a867d', marginTop: 2 }}>{c.repair_summary}</div>
                )}
                {c.key_steps.length > 0 && (
                  <div style={{ color: '#8a867d', marginTop: 2 }}>
                    步骤：{c.key_steps.join('；')}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
        <Form.Item name="responsible_person_id" label="责任人" rules={[{ required: true, message: '请选择责任人' }]}>
          <Select
            placeholder="选择责任人"
            showSearch
            optionFilterProp="label"
            options={maintainers.map((m) => ({
              label: `${m.name} (${m.employee_no || '-'})`,
              value: m.user_id,
            }))}
          />
        </Form.Item>
        <Form.Item label="故障图片">
          <Upload
            listType="picture-card"
            fileList={fileList}
            onChange={({ fileList: newList }) => setFileList(newList)}
            beforeUpload={() => false}
            maxCount={9}
            accept="image/*"
          >
            {fileList.length < 9 && (
              <div>
                <PlusOutlined />
                <div style={{ marginTop: 8 }}>上传</div>
              </div>
            )}
          </Upload>
        </Form.Item>
      </Form>
    </Drawer>
  )
}
