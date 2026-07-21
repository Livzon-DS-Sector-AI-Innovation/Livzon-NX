'use client'

import { useMemo, useState } from 'react'
import dayjs from 'dayjs'
import type { Dayjs } from 'dayjs'
import {
  App,
  Button,
  DatePicker,
  Divider,
  Form,
  Input,
  InputNumber,
  Space,
  Tag,
} from 'antd'
import {
  DeleteOutlined,
  DownloadOutlined,
  PlusOutlined,
} from '@ant-design/icons'
import { generateProcurementContract } from '@/actions/purchasing'
import type { ContractCategory, ContractGenerateRequest } from '@/types/purchasing'

type ContractGenerationClientProps = {
  category: ContractCategory
  categoryLabel: string
}

type ContractFormValues = Omit<
  ContractGenerateRequest,
  'category' | 'contract_date' | 'delivery_date'
> & {
  contract_date: Dayjs
  delivery_date?: Dayjs
}

const defaultPaymentTerms: Record<string, string> = {
  'raw-materials': '货到验收合格后，凭卖方开具的增值税发票30天内以银行承兑汇票支付货款',
  consumables: '买方收货且检验合格后30天以6个月承兑汇票方式付款',
  hardware: '收到货并验收无误后，卖方开具全额增值税专用发票，买方收货后150日内以6个月承兑方式支付',
  'fixed-assets': '货到验收完成后30个工作日内支付90%，质保期满后支付10%',
}

const defaultItems = {
  'raw-materials': {
    item_code: '',
    name: '',
    specification: '',
    quality_standard: '',
    manufacturer: '',
    department: '',
    quantity: 1,
    unit: '吨',
    unit_price: 0,
    amount: null,
    remarks: '/',
  },
  consumables: {
    item_code: '',
    name: '',
    specification: '',
    quality_standard: '',
    manufacturer: '',
    department: '',
    quantity: 1,
    unit: '个',
    unit_price: 0,
    amount: null,
    remarks: '',
  },
  hardware: {
    item_code: '',
    name: '',
    specification: '',
    quality_standard: '',
    manufacturer: '',
    department: '',
    quantity: 1,
    unit: '个',
    unit_price: 0,
    amount: null,
    remarks: '',
  },
  'fixed-assets': {
    item_code: '',
    name: '',
    specification: '',
    quality_standard: '',
    manufacturer: '',
    department: '',
    quantity: 1,
    unit: '台',
    unit_price: 0,
    amount: null,
    remarks: '',
  },
} as const

function downloadBase64File(base64: string, filename: string, contentType: string) {
  const binary = window.atob(base64)
  const bytes = new Uint8Array(binary.length)
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index)
  }
  const blob = new Blob([bytes], { type: contentType })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

function toDateString(value?: Dayjs) {
  return value ? value.format('YYYY-MM-DD') : undefined
}

export function ContractGenerationClient({
  category,
  categoryLabel,
}: ContractGenerationClientProps) {
  const { message } = App.useApp()
  const [form] = Form.useForm<ContractFormValues>()
  const [generating, setGenerating] = useState(false)
  const isFixedAssets = category === 'fixed-assets'
  const isConsumables = category === 'consumables'
  const isHardware = category === 'hardware'

  const initialValues = useMemo<Partial<ContractFormValues>>(
    () => ({
      title: '',
      contract_date: dayjs(),
      tax_rate: 13,
      payment_terms: defaultPaymentTerms[category],
      buyer_invoice_recipient: '',
      buyer_invoice_recipient_mobile: '',
      buyer_receiver: '',
      buyer_receiver_mobile: '',
      buyer_receiver_phone: '',
      seller: {
        name: '',
        representative: '',
        address: '',
        postal_code: '',
        contact_person: '',
        contact_address: '',
        contact_phone: '',
        mobile: '',
        phone: '',
        bank_name: '',
        bank_account: '',
        tax_id: '',
        bank_line_number: '',
        email: '',
      },
      items: [defaultItems[category]],
      attached_documents: 'A、B、C',
      installation_days: 5,
      warranty_months: 12,
      response_hours: 24,
      onsite_hours: 48,
      maintenance_response_hours: 48,
      overdue_days: isFixedAssets ? 2 : 20,
      jurisdiction: '广东省珠海市金湾区',
      copies: 2,
      buyer_copies: 1,
      arrival_payment_condition: '货到验收完成后30',
      arrival_payment_method: '6个月承兑汇票',
      arrival_payment_ratio: 90,
      warranty_payment_ratio: 10,
      warranty_payment_method: '承兑',
    }),
    [category, isFixedAssets]
  )

  const handleFinish = async (values: ContractFormValues) => {
    setGenerating(true)
    const payload: ContractGenerateRequest = {
      ...values,
      category,
      contract_date: toDateString(values.contract_date) || dayjs().format('YYYY-MM-DD'),
      delivery_date: toDateString(values.delivery_date) || null,
      items: values.items.map((item) => ({
        ...item,
        amount: item.amount ?? null,
      })),
    }

    try {
      const result = await generateProcurementContract(payload)
      if (!result.ok) {
        message.error(result.message)
        return
      }
      downloadBase64File(result.base64, result.filename, result.contentType)
      message.success('合同已生成')
    } catch {
      message.error('合同生成失败，请稍后重试')
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="mb-2 text-[13px] text-[var(--color-stone)]">采购管理 / 合同生成</p>
          <h1 className="mb-2 text-[22px] font-semibold text-[var(--color-charcoal)]">
            {categoryLabel}合同生成
          </h1>
          <div className="flex flex-wrap gap-2">
            <Tag color="purple">模板：{categoryLabel}</Tag>
            <Tag color="blue">自动汇总金额</Tag>
            <Tag color="green">生成 Word</Tag>
          </div>
        </div>
      </div>

      <Form
        form={form}
        layout="vertical"
        initialValues={initialValues}
        onFinish={handleFinish}
        className="space-y-4"
      >
        <section className="rounded-[12px] border border-[var(--color-hairline)] bg-[var(--color-canvas)] p-6">
          <div className="grid gap-4 md:grid-cols-4">
            <Form.Item
              name="title"
              label="合同标题"
              rules={[{ required: true, message: '请输入合同标题' }]}
              className="md:col-span-2"
            >
              <Input placeholder="例如：2026年7月耗材采购合同" />
            </Form.Item>
            <Form.Item
              name="contract_number"
              label="合同编号"
              rules={[{ required: true, message: '请输入合同编号' }]}
            >
              <Input placeholder="LZNX..." />
            </Form.Item>
            <Form.Item
              name="contract_date"
              label="签订日期"
              rules={[{ required: true, message: '请选择签订日期' }]}
            >
              <DatePicker className="w-full" />
            </Form.Item>
            <Form.Item name="delivery_date" label="最迟交货日期">
              <DatePicker className="w-full" />
            </Form.Item>
            <Form.Item name="tax_rate" label="税率（%）">
              <InputNumber className="w-full" min={0} max={100} precision={2} />
            </Form.Item>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <Form.Item name="delivery_terms" label="交货说明">
              <Input.TextArea rows={3} />
            </Form.Item>
            <Form.Item name="payment_terms" label="付款期限/方式">
              <Input.TextArea rows={3} />
            </Form.Item>
          </div>
        </section>

        <section className="rounded-[12px] border border-[var(--color-hairline)] bg-[var(--color-canvas)] p-6">
          <h2 className="mb-4 text-[18px] font-semibold text-[var(--color-charcoal)]">
            {isConsumables ? '卖方及买方信息' : '卖方信息'}
          </h2>
          {isConsumables ? (
            <div className="grid gap-4 lg:grid-cols-2">
              <div className="overflow-hidden rounded-[8px] border border-[var(--color-hairline)]">
                <div className="grid border-b border-[var(--color-hairline)] md:grid-cols-[160px_minmax(0,1fr)]">
                  <div className="flex items-center bg-[var(--color-surface-soft)] px-4 py-3 text-[14px] font-medium text-[var(--color-charcoal)]">
                    卖方（必须盖章）
                  </div>
                  <div className="px-4 py-3">
                    <Form.Item
                      name={['seller', 'name']}
                      rules={[{ required: true, message: '请输入卖方名称' }]}
                      noStyle
                    >
                      <Input />
                    </Form.Item>
                  </div>
                </div>
                <div className="grid border-b border-[var(--color-hairline)] md:grid-cols-[160px_minmax(0,1fr)]">
                  <div className="flex items-center bg-[var(--color-surface-soft)] px-4 py-3 text-[14px] font-medium text-[var(--color-charcoal)]">
                    代表人
                  </div>
                  <div className="px-4 py-3">
                    <Form.Item name={['seller', 'representative']} noStyle>
                      <Input />
                    </Form.Item>
                  </div>
                </div>
                <div className="grid border-b border-[var(--color-hairline)] md:grid-cols-[160px_minmax(0,1fr)]">
                  <div className="flex bg-[var(--color-surface-soft)] px-4 py-4 text-[14px] font-medium text-[var(--color-charcoal)]">
                    单位开票信息
                  </div>
                  <div className="grid gap-x-4 gap-y-3 px-4 py-4 md:grid-cols-2">
                    <Form.Item name={['seller', 'address']} label="地址" className="mb-0 md:col-span-2">
                      <Input />
                    </Form.Item>
                    <Form.Item name={['seller', 'bank_name']} label="开户行" className="mb-0">
                      <Input />
                    </Form.Item>
                    <Form.Item name={['seller', 'bank_account']} label="账号" className="mb-0">
                      <Input />
                    </Form.Item>
                    <Form.Item name={['seller', 'phone']} label="电话" className="mb-0">
                      <Input />
                    </Form.Item>
                    <Form.Item name={['seller', 'tax_id']} label="税务登记号" className="mb-0">
                      <Input />
                    </Form.Item>
                  </div>
                </div>
                <div className="grid md:grid-cols-[160px_minmax(0,1fr)]">
                  <div className="flex bg-[var(--color-surface-soft)] px-4 py-4 text-[14px] font-medium text-[var(--color-charcoal)]">
                    质量联系人
                  </div>
                  <div className="grid gap-x-4 gap-y-3 px-4 py-4 md:grid-cols-2">
                    <Form.Item name={['seller', 'contact_person']} label="代表人姓名" className="mb-0">
                      <Input />
                    </Form.Item>
                    <Form.Item name={['seller', 'mobile']} label="手机" className="mb-0">
                      <Input />
                    </Form.Item>
                    <Form.Item name={['seller', 'email']} label="收合同邮箱" className="mb-0">
                      <Input />
                    </Form.Item>
                    <Form.Item name={['seller', 'contact_address']} label="地址" className="mb-0 md:col-span-2">
                      <Input />
                    </Form.Item>
                  </div>
                </div>
              </div>

              <div className="overflow-hidden rounded-[8px] border border-[var(--color-hairline)]">
                <div className="grid border-b border-[var(--color-hairline)] md:grid-cols-[160px_minmax(0,1fr)]">
                  <div className="flex items-center bg-[var(--color-surface-soft)] px-4 py-3 text-[14px] font-medium text-[var(--color-charcoal)]">
                    买方（必须盖章）
                  </div>
                  <div className="px-4 py-3 text-[14px] text-[var(--color-charcoal)]">
                    丽珠集团（宁夏）制药有限公司
                  </div>
                </div>
                <div className="grid border-b border-[var(--color-hairline)] md:grid-cols-[160px_minmax(0,1fr)]">
                  <div className="flex items-center bg-[var(--color-surface-soft)] px-4 py-3 text-[14px] font-medium text-[var(--color-charcoal)]">
                    代表人
                  </div>
                  <div className="px-4 py-3 text-[14px] text-[var(--color-stone)]">按模板保留</div>
                </div>
                <div className="grid border-b border-[var(--color-hairline)] md:grid-cols-[160px_minmax(0,1fr)]">
                  <div className="flex bg-[var(--color-surface-soft)] px-4 py-4 text-[14px] font-medium text-[var(--color-charcoal)]">
                    买方开票信息
                  </div>
                  <div className="whitespace-pre-line px-4 py-4 text-[14px] leading-7 text-[var(--color-charcoal)]">
                    地址：宁夏平罗县太沙工业园区{'\n'}
                    开户行：中国工商银行股份有限公司平罗星海支行{'\n'}
                    账号：2904000919200004252{'\n'}
                    电话：0952-6296656{'\n'}
                    税号：91640221574877733M
                  </div>
                </div>
                <div className="grid md:grid-cols-[160px_minmax(0,1fr)]">
                  <div className="flex bg-[var(--color-surface-soft)] px-4 py-4 text-[14px] font-medium text-[var(--color-charcoal)]">
                    发票及收货信息
                  </div>
                  <div className="grid gap-x-4 gap-y-3 px-4 py-4 md:grid-cols-2">
                    <Form.Item name="buyer_invoice_recipient" label="接收人" className="mb-0">
                      <Input />
                    </Form.Item>
                    <Form.Item name="buyer_invoice_recipient_mobile" label="接收人手机" className="mb-0">
                      <Input />
                    </Form.Item>
                    <div className="md:col-span-2 text-[13px] leading-6 text-[var(--color-slate)]">
                      发票地址：宁夏石嘴山市平罗太沙工业园丽珠制药
                    </div>
                    <Form.Item name="buyer_receiver" label="收货人" className="mb-0">
                      <Input />
                    </Form.Item>
                    <Form.Item name="buyer_receiver_mobile" label="收货人手机" className="mb-0">
                      <Input />
                    </Form.Item>
                    <Form.Item name="buyer_receiver_phone" label="收货人电话" className="mb-0">
                      <Input />
                    </Form.Item>
                    <div className="md:col-span-2 text-[13px] leading-6 text-[var(--color-slate)]">
                      收货地址：宁夏石嘴山市平罗太沙工业园丽珠制药
                    </div>
                  </div>
                </div>
              </div>
            </div>
          ) : isHardware ? (
            <div className="overflow-hidden rounded-[8px] border border-[var(--color-hairline)]">
              <div className="grid border-b border-[var(--color-hairline)] md:grid-cols-[190px_minmax(0,1fr)]">
                <div className="flex items-center bg-[var(--color-surface-soft)] px-4 py-3 text-[14px] font-medium text-[var(--color-charcoal)]">
                  卖方（必须盖章）
                </div>
                <div className="px-4 py-3">
                  <Form.Item
                    name={['seller', 'name']}
                    rules={[{ required: true, message: '请输入卖方名称' }]}
                    noStyle
                  >
                    <Input />
                  </Form.Item>
                </div>
              </div>
              <div className="grid border-b border-[var(--color-hairline)] md:grid-cols-[190px_minmax(0,1fr)]">
                <div className="flex items-center bg-[var(--color-surface-soft)] px-4 py-3 text-[14px] font-medium text-[var(--color-charcoal)]">
                  代表人
                </div>
                <div className="px-4 py-3">
                  <Form.Item name={['seller', 'representative']} noStyle>
                    <Input />
                  </Form.Item>
                </div>
              </div>
              <div className="grid border-b border-[var(--color-hairline)] md:grid-cols-[190px_minmax(0,1fr)]">
                <div className="flex bg-[var(--color-surface-soft)] px-4 py-4 text-[14px] font-medium text-[var(--color-charcoal)]">
                  单位开票信息
                </div>
                <div className="grid gap-x-4 gap-y-3 px-4 py-4 md:grid-cols-2">
                  <Form.Item name={['seller', 'address']} label="地址" className="mb-0 md:col-span-2">
                    <Input />
                  </Form.Item>
                  <Form.Item name={['seller', 'bank_name']} label="开户行" className="mb-0">
                    <Input />
                  </Form.Item>
                  <Form.Item name={['seller', 'bank_account']} label="账号" className="mb-0">
                    <Input />
                  </Form.Item>
                  <Form.Item name={['seller', 'phone']} label="电话" className="mb-0">
                    <Input />
                  </Form.Item>
                  <Form.Item name={['seller', 'postal_code']} label="邮编" className="mb-0">
                    <Input />
                  </Form.Item>
                  <Form.Item name={['seller', 'tax_id']} label="税务登记号" className="mb-0 md:col-span-2">
                    <Input />
                  </Form.Item>
                </div>
              </div>
              <div className="grid md:grid-cols-[190px_minmax(0,1fr)]">
                <div className="flex bg-[var(--color-surface-soft)] px-4 py-4 text-[14px] font-medium text-[var(--color-charcoal)]">
                  合同联系人信息
                </div>
                <div className="grid gap-x-4 gap-y-3 px-4 py-4 md:grid-cols-2">
                  <Form.Item name={['seller', 'contact_person']} label="代表人姓名" className="mb-0">
                    <Input />
                  </Form.Item>
                  <Form.Item name={['seller', 'contact_phone']} label="电话" className="mb-0">
                    <Input />
                  </Form.Item>
                  <Form.Item name={['seller', 'mobile']} label="手机" className="mb-0">
                    <Input />
                  </Form.Item>
                  <Form.Item name={['seller', 'email']} label="收合同邮箱" className="mb-0">
                    <Input />
                  </Form.Item>
                  <Form.Item name={['seller', 'contact_address']} label="地址" className="mb-0 md:col-span-2">
                    <Input />
                  </Form.Item>
                </div>
              </div>
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-3">
              <Form.Item
                name={['seller', 'name']}
                label="卖方名称"
                rules={[{ required: true, message: '请输入卖方名称' }]}
              >
                <Input />
              </Form.Item>
              <Form.Item name={['seller', 'contact_person']} label="联系人">
                <Input />
              </Form.Item>
              <Form.Item name={['seller', 'phone']} label="电话">
                <Input />
              </Form.Item>
              <Form.Item name={['seller', 'postal_code']} label="邮编">
                <Input />
              </Form.Item>
              <Form.Item name={['seller', 'tax_id']} label="税号/统一社会信用代码">
                <Input />
              </Form.Item>
              <Form.Item name={['seller', 'bank_name']} label="开户行">
                <Input />
              </Form.Item>
              <Form.Item name={['seller', 'bank_account']} label="账号">
                <Input />
              </Form.Item>
              {isFixedAssets && (
                <Form.Item name={['seller', 'bank_line_number']} label="银行行号">
                  <Input />
                </Form.Item>
              )}
              <Form.Item name={['seller', 'email']} label="邮箱">
                <Input />
              </Form.Item>
              <Form.Item name={['seller', 'address']} label="地址" className="md:col-span-3">
                <Input />
              </Form.Item>
            </div>
          )}
        </section>

        {isFixedAssets && (
          <section className="rounded-[12px] border border-[var(--color-hairline)] bg-[var(--color-canvas)] p-6">
            <h2 className="mb-4 text-[18px] font-semibold text-[var(--color-charcoal)]">固定资产条款</h2>
            <div className="grid gap-4 md:grid-cols-4">
              <Form.Item name="attached_documents" label="随货资料">
                <Input />
              </Form.Item>
              <Form.Item name="installation_days" label="安装调试天数">
                <InputNumber className="w-full" min={0} precision={0} />
              </Form.Item>
              <Form.Item name="warranty_months" label="质保期（月）">
                <InputNumber className="w-full" min={0} precision={0} />
              </Form.Item>
              <Form.Item name="overdue_days" label="逾期解除天数">
                <InputNumber className="w-full" min={0} precision={0} />
              </Form.Item>
              <Form.Item name="response_hours" label="质保响应小时">
                <InputNumber className="w-full" min={0} precision={0} />
              </Form.Item>
              <Form.Item name="onsite_hours" label="到场处理小时">
                <InputNumber className="w-full" min={0} precision={0} />
              </Form.Item>
              <Form.Item name="maintenance_response_hours" label="期满维修响应小时">
                <InputNumber className="w-full" min={0} precision={0} />
              </Form.Item>
              <Form.Item name="jurisdiction" label="争议管辖地">
                <Input />
              </Form.Item>
              <Form.Item name="arrival_payment_condition" label="到货款支付条件">
                <Input />
              </Form.Item>
              <Form.Item name="arrival_payment_method" label="到货款支付方式">
                <Input />
              </Form.Item>
              <Form.Item name="arrival_payment_ratio" label="到货款比例（%）">
                <InputNumber className="w-full" min={0} max={100} precision={2} />
              </Form.Item>
              <Form.Item name="warranty_payment_ratio" label="质保金比例（%）">
                <InputNumber className="w-full" min={0} max={100} precision={2} />
              </Form.Item>
              <Form.Item name="warranty_payment_method" label="质保金支付方式">
                <Input />
              </Form.Item>
              <Form.Item name="copies" label="合同总份数">
                <InputNumber className="w-full" min={1} precision={0} />
              </Form.Item>
              <Form.Item name="buyer_copies" label="买方执份数">
                <InputNumber className="w-full" min={1} precision={0} />
              </Form.Item>
              <Form.Item name="attachment_note" label="附件说明" className="md:col-span-2">
                <Input />
              </Form.Item>
            </div>
          </section>
        )}

        <section className="rounded-[12px] border border-[var(--color-hairline)] bg-[var(--color-canvas)] p-6">
          <div className="mb-4 flex items-center justify-between gap-4">
            <h2 className="text-[18px] font-semibold text-[var(--color-charcoal)]">合同明细</h2>
          </div>
          <Form.List name="items">
            {(fields, { add, remove }) => (
              <div className="space-y-4">
                {fields.map((field, index) => (
                  <div
                    key={field.key}
                    className="rounded-[8px] border border-[var(--color-hairline-soft)] bg-[var(--color-surface-soft)] p-4"
                  >
                    <div className="mb-3 flex items-center justify-between gap-3">
                      <div className="text-[14px] font-semibold text-[var(--color-charcoal)]">
                        明细 {index + 1}
                      </div>
                      {fields.length > 1 && (
                        <Button
                          icon={<DeleteOutlined />}
                          onClick={() => remove(field.name)}
                        >
                          删除
                        </Button>
                      )}
                    </div>
                    <div className="grid gap-3 md:grid-cols-6">
                      {(category === 'raw-materials' || category === 'hardware') && (
                        <Form.Item name={[field.name, 'item_code']} label="编码">
                          <Input />
                        </Form.Item>
                      )}
                      <Form.Item
                        name={[field.name, 'name']}
                        label="名称"
                        rules={[{ required: true, message: '请输入名称' }]}
                        className="md:col-span-2"
                      >
                        <Input />
                      </Form.Item>
                      <Form.Item name={[field.name, 'specification']} label="规格">
                        <Input />
                      </Form.Item>
                      {category === 'raw-materials' && (
                        <Form.Item name={[field.name, 'quality_standard']} label="质量标准">
                          <Input />
                        </Form.Item>
                      )}
                      {(category === 'raw-materials' || category === 'fixed-assets') && (
                        <Form.Item name={[field.name, 'manufacturer']} label="生产厂家">
                          <Input />
                        </Form.Item>
                      )}
                      {(category === 'consumables' || category === 'hardware') && (
                        <Form.Item name={[field.name, 'department']} label="部门">
                          <Input />
                        </Form.Item>
                      )}
                      <Form.Item
                        name={[field.name, 'quantity']}
                        label="数量"
                        rules={[{ required: true, message: '请输入数量' }]}
                      >
                        <InputNumber className="w-full" min={0} precision={4} />
                      </Form.Item>
                      <Form.Item name={[field.name, 'unit']} label="单位">
                        <Input />
                      </Form.Item>
                      <Form.Item
                        name={[field.name, 'unit_price']}
                        label="单价"
                        rules={[{ required: true, message: '请输入单价' }]}
                      >
                        <InputNumber className="w-full" min={0} precision={4} />
                      </Form.Item>
                      <Form.Item name={[field.name, 'amount']} label="总金额">
                        <InputNumber className="w-full" min={0} precision={2} />
                      </Form.Item>
                      <Form.Item name={[field.name, 'remarks']} label="备注" className="md:col-span-2">
                        <Input />
                      </Form.Item>
                    </div>
                  </div>
                ))}
                <Button
                  icon={<PlusOutlined />}
                  onClick={() => add(defaultItems[category])}
                >
                  新增明细
                </Button>
              </div>
            )}
          </Form.List>
        </section>

        <section className="rounded-[12px] border border-[var(--color-hairline)] bg-[var(--color-canvas)] p-6">
          <div className="flex flex-wrap items-center justify-end gap-4">
            <Space separator={<Divider orientation="vertical" />}>
              <Button onClick={() => form.resetFields()}>重置</Button>
              <Button
                type="primary"
                htmlType="submit"
                icon={<DownloadOutlined />}
                loading={generating}
              >
                生成合同
              </Button>
            </Space>
          </div>
        </section>
      </Form>
    </div>
  )
}
