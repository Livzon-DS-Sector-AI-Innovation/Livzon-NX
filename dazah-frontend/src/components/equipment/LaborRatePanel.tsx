'use client'

// 维修工时费率配置（方案C）：人员级（优先）/岗位级 CRUD。
// 工时成本 = 完成工单时的维修时长 × 该维修人费率（person > role > 0）。

import { useCallback, useEffect, useState } from 'react'
import { App, Button, Form, InputNumber, Modal, Popconfirm, Radio, Select, Space, Table, DatePicker, Input } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs, { type Dayjs } from 'dayjs'
import type { LaborRate } from '@/types/equipment'
import type { EquipmentRole } from '@/types/equipment-personnel'
import { fetchLaborRatesClient, fetchAllUsersClient } from '@/lib/api/equipment-client'
import { fetchRoles } from '@/lib/api/equipment-personnel'
import { deleteLaborRate, saveLaborRate } from '@/actions/equipment'
import type { Maintainer } from '@/types/equipment'

interface RateFormValues {
  scope: 'role' | 'person'
  target_id: string
  hourly_rate: number
  effective_from: Dayjs | null
  remark?: string
}

export function LaborRatePanel() {
  const { message } = App.useApp()
  const [rates, setRates] = useState<LaborRate[]>([])
  const [loading, setLoading] = useState(true)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [roles, setRoles] = useState<EquipmentRole[]>([])
  const [users, setUsers] = useState<Maintainer[]>([])
  const [form] = Form.useForm<RateFormValues>()
  const scope = Form.useWatch('scope', form)

  const load = useCallback(async () => {
    const [rateList] = await Promise.all([
      fetchLaborRatesClient().catch(() => null),
      fetchRoles().then((r) => setRoles(r)).catch(() => setRoles([])),
      fetchAllUsersClient()
        .then((u) => setUsers(u))
        .catch(() => setUsers([])),
    ])
    setRates(rateList ?? [])
    setLoading(false)
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const openCreate = () => {
    setEditingId(null)
    form.resetFields()
    form.setFieldsValue({ scope: 'person', hourly_rate: 50, effective_from: dayjs() })
    setDrawerOpen(true)
  }

  const openEdit = (record: LaborRate) => {
    setEditingId(record.id)
    form.setFieldsValue({
      scope: record.scope,
      target_id: (record.scope === 'role' ? record.role_id : record.person_id) ?? undefined,
      hourly_rate: record.hourly_rate,
      effective_from: record.effective_from ? dayjs(record.effective_from) : dayjs(),
      remark: record.remark ?? undefined,
    })
    setDrawerOpen(true)
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      setSubmitting(true)
      await saveLaborRate({
        scope: values.scope,
        role_id: values.scope === 'role' ? values.target_id : null,
        person_id: values.scope === 'person' ? values.target_id : null,
        hourly_rate: values.hourly_rate,
        effective_from: values.effective_from?.format('YYYY-MM-DD') ?? null,
        remark: values.remark ?? null,
      })
      message.success(editingId ? '费率已更新' : '费率已新增')
      setDrawerOpen(false)
      await load()
    } catch (e) {
      if (e instanceof Error && e.message) message.error(e.message)
    } finally {
      setSubmitting(false)
    }
  }

  const columns: ColumnsType<LaborRate> = [
    {
      title: '范围',
      dataIndex: 'scope',
      key: 'scope',
      width: 100,
      render: (s: string) => (s === 'person' ? '人员级（优先）' : '岗位级'),
    },
    {
      title: '目标',
      key: 'target',
      width: 200,
      render: (_: unknown, r) => {
        if (r.scope === 'person') {
          const u = users.find((x) => x.user_id === r.person_id)
          return u ? `${u.name}（${u.employee_no || '-'}）` : r.person_id?.slice(0, 8) ?? '-'
        }
        const role = roles.find((x) => x.id === r.role_id)
        return role ? role.name : r.role_id?.slice(0, 8) ?? '-'
      },
    },
    {
      title: '时薪（元/小时）',
      dataIndex: 'hourly_rate',
      key: 'hourly_rate',
      width: 130,
      render: (v: number) => `¥${v.toFixed(2)}`,
    },
    { title: '生效日期', dataIndex: 'effective_from', key: 'effective_from', width: 110 },
    { title: '备注', dataIndex: 'remark', key: 'remark', ellipsis: true, render: (v: string | null) => v || '-' },
    {
      title: '操作',
      key: 'actions',
      width: 140,
      render: (_: unknown, r) => (
        <Space size={4}>
          <Button size="small" onClick={() => openEdit(r)}>
            编辑
          </Button>
          <Popconfirm
            title="确认删除该费率？"
            onConfirm={async () => {
              try {
                await deleteLaborRate(r.id)
                message.success('已删除')
                await load()
              } catch (e) {
                message.error(e instanceof Error ? e.message : '删除失败')
              }
            }}
          >
            <Button size="small" danger>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div data-testid="labor-rate-panel">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <span style={{ color: '#8a867d', fontSize: 12 }}>
          工时成本按「人员费率 &gt; 岗位费率 &gt; 0」解析；未配置人员的工单工时成本记 0
        </span>
        <Button type="primary" onClick={openCreate}>
          新增费率
        </Button>
      </div>
      <Table<LaborRate>
        size="small"
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={rates}
        pagination={false}
        locale={{ emptyText: '暂无费率配置，工单完成时工时成本将记 0' }}
      />

      <Modal
        title={editingId ? '编辑费率' : '新增费率'}
        open={drawerOpen}
        onCancel={() => setDrawerOpen(false)}
        onOk={handleSubmit}
        confirmLoading={submitting}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" requiredMark="optional">
          <Form.Item name="scope" label="费率范围" rules={[{ required: true }]}>
            <Radio.Group
              disabled={!!editingId}
              options={[
                { label: '人员级（优先）', value: 'person' },
                { label: '岗位级', value: 'role' },
              ]}
            />
          </Form.Item>
          <Form.Item
            name="target_id"
            label={scope === 'role' ? '设备角色' : '人员'}
            rules={[{ required: true, message: scope === 'role' ? '请选择角色' : '请选择人员' }]}
          >
            {scope === 'role' ? (
              <Select
                placeholder="选择设备角色（人员配置中维护）"
                showSearch
                optionFilterProp="label"
                options={roles.map((r) => ({ label: r.name, value: r.id }))}
              />
            ) : (
              <Select
                placeholder="选择人员"
                showSearch
                optionFilterProp="label"
                options={users.map((u) => ({
                  label: `${u.name}（${u.employee_no || '-'}）`,
                  value: u.user_id,
                }))}
              />
            )}
          </Form.Item>
          <Form.Item name="hourly_rate" label="时薪（元/小时）" rules={[{ required: true }]}>
            <InputNumber min={0} precision={2} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="effective_from" label="生效日期">
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="remark" label="备注">
            <Input maxLength={200} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
