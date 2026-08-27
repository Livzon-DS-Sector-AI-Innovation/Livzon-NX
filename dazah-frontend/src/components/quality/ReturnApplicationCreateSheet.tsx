'use client'

import type { CSSProperties } from 'react'
import type { Dayjs } from 'dayjs'
import { DatePicker, Form, Input, Select, Typography } from 'antd'
import type { FormInstance } from 'antd'

export interface ReturnApplicationFormValues {
  serial_number: string
  product_name: string
  return_total: string
  specification: string
  batch_number: string
  quantity: string
  production_date: string
  expiry_date: string
  batch_number1: string
  quantity1: string
  production_date1: string
  expiry_date1: string
  batch_number2: string
  quantity2: string
  production_date2: string
  expiry_date2: string
  return_unit_address: string
  return_reason: string
  applicant: string
  application_date: Dayjs | null
  qa_head_opinion: string
  qa_head: string
  qa_head_date: Dayjs | null
  quality_manager_suggestion: string
  quality_manager: string
  quality_manager_date: Dayjs | null
  remark: string
}

interface ContactOption {
  label: string
  value: string
}

interface ReturnApplicationCreateSheetProps {
  form: FormInstance<ReturnApplicationFormValues>
  contactOptions: ContactOption[]
}

const outerStyle: CSSProperties = {
  border: '1px solid #1f1f1f',
  background: '#fff',
}

const tableStyle: CSSProperties = {
  width: '100%',
  borderCollapse: 'collapse',
  tableLayout: 'fixed',
}

const cellStyle: CSSProperties = {
  border: '1px solid #1f1f1f',
  padding: 6,
  fontSize: 12,
  verticalAlign: 'middle',
}

const centerCellStyle: CSSProperties = {
  ...cellStyle,
  textAlign: 'center',
}

const labelCellStyle: CSSProperties = {
  ...centerCellStyle,
  width: 72,
  fontWeight: 600,
  background: '#fafafa',
}

const textAreaCellStyle: CSSProperties = {
  ...cellStyle,
  padding: 0,
}

const noMarginItemStyle: CSSProperties = {
  marginBottom: 0,
}

function buildSelect(searchPlaceholder: string, options: ContactOption[]) {
  return (
    <Select
      allowClear
      showSearch
      placeholder={searchPlaceholder}
      options={options}
      optionFilterProp="label"
      style={{ width: '100%' }}
      getPopupContainer={(triggerNode) => triggerNode.parentElement || document.body}
    />
  )
}

export default function ReturnApplicationCreateSheet({
  form,
  contactOptions,
}: ReturnApplicationCreateSheetProps) {
  return (
    <div style={outerStyle}>
      <div style={{ padding: '12px 16px 4px' }}>
        <Typography.Title level={4} style={{ margin: 0, textAlign: 'center', letterSpacing: 1 }}>
          退货申请单
        </Typography.Title>
      </div>

      <Form form={form} layout="vertical">
        <table style={tableStyle}>
          <colgroup>
            <col style={{ width: 68 }} />
            <col style={{ width: '20%' }} />
            <col style={{ width: '12%' }} />
            <col style={{ width: '15%' }} />
            <col style={{ width: '18%' }} />
            <col style={{ width: 72 }} />
            <col style={{ width: '23%' }} />
          </colgroup>
          <tbody>
            <tr>
              <td style={labelCellStyle}>品名</td>
              <td style={cellStyle} colSpan={2}>
                <Form.Item
                  name="product_name"
                  rules={[{ required: true, message: '请输入品名' }]}
                  style={noMarginItemStyle}
                >
                  <Input variant="borderless" placeholder="请输入品名" />
                </Form.Item>
              </td>
              <td style={labelCellStyle}>退货总量</td>
              <td style={cellStyle}>
                <Form.Item name="return_total" style={noMarginItemStyle}>
                  <Input variant="borderless" placeholder="请输入退货总量" />
                </Form.Item>
              </td>
              <td style={labelCellStyle}>规格</td>
              <td style={cellStyle}>
                <Form.Item name="specification" style={noMarginItemStyle}>
                  <Input variant="borderless" placeholder="请输入规格" />
                </Form.Item>
              </td>
            </tr>

            <tr>
              <td style={labelCellStyle} rowSpan={4}>退货明细</td>
              <td style={centerCellStyle}>批号</td>
              <td style={centerCellStyle}>数量</td>
              <td style={centerCellStyle}>生产日期</td>
              <td style={centerCellStyle}>有效期/复验期</td>
              <td style={labelCellStyle} rowSpan={4}>备注</td>
              <td style={textAreaCellStyle} rowSpan={4}>
                <Form.Item name="remark" style={noMarginItemStyle}>
                  <Input.TextArea
                    variant="borderless"
                    placeholder="请输入备注"
                    autoSize={{ minRows: 7, maxRows: 7 }}
                  />
                </Form.Item>
              </td>
            </tr>

            <tr>
              <td style={cellStyle}>
                <Form.Item name="batch_number" style={noMarginItemStyle}>
                  <Input variant="borderless" placeholder="批号" />
                </Form.Item>
              </td>
              <td style={cellStyle}>
                <Form.Item name="quantity" style={noMarginItemStyle}>
                  <Input variant="borderless" placeholder="数量" />
                </Form.Item>
              </td>
              <td style={cellStyle}>
                <Form.Item name="production_date" style={noMarginItemStyle}>
                  <Input variant="borderless" placeholder="生产日期" />
                </Form.Item>
              </td>
              <td style={cellStyle}>
                <Form.Item name="expiry_date" style={noMarginItemStyle}>
                  <Input variant="borderless" placeholder="有效期/复验期" />
                </Form.Item>
              </td>
            </tr>

            <tr>
              <td style={cellStyle}>
                <Form.Item name="batch_number1" style={noMarginItemStyle}>
                  <Input variant="borderless" placeholder="批号" />
                </Form.Item>
              </td>
              <td style={cellStyle}>
                <Form.Item name="quantity1" style={noMarginItemStyle}>
                  <Input variant="borderless" placeholder="数量" />
                </Form.Item>
              </td>
              <td style={cellStyle}>
                <Form.Item name="production_date1" style={noMarginItemStyle}>
                  <Input variant="borderless" placeholder="生产日期" />
                </Form.Item>
              </td>
              <td style={cellStyle}>
                <Form.Item name="expiry_date1" style={noMarginItemStyle}>
                  <Input variant="borderless" placeholder="有效期/复验期" />
                </Form.Item>
              </td>
            </tr>

            <tr>
              <td style={cellStyle}>
                <Form.Item name="batch_number2" style={noMarginItemStyle}>
                  <Input variant="borderless" placeholder="批号" />
                </Form.Item>
              </td>
              <td style={cellStyle}>
                <Form.Item name="quantity2" style={noMarginItemStyle}>
                  <Input variant="borderless" placeholder="数量" />
                </Form.Item>
              </td>
              <td style={cellStyle}>
                <Form.Item name="production_date2" style={noMarginItemStyle}>
                  <Input variant="borderless" placeholder="生产日期" />
                </Form.Item>
              </td>
              <td style={cellStyle}>
                <Form.Item name="expiry_date2" style={noMarginItemStyle}>
                  <Input variant="borderless" placeholder="有效期/复验期" />
                </Form.Item>
              </td>
            </tr>

            <tr>
              <td style={labelCellStyle}>退货单位及地址</td>
              <td style={textAreaCellStyle} colSpan={6}>
                <Form.Item name="return_unit_address" style={noMarginItemStyle}>
                  <Input.TextArea
                    variant="borderless"
                    placeholder="请输入退货单位及地址"
                    autoSize={{ minRows: 3, maxRows: 3 }}
                  />
                </Form.Item>
              </td>
            </tr>

            <tr>
              <td style={labelCellStyle}>退货原因</td>
              <td style={textAreaCellStyle} colSpan={6}>
                <Form.Item name="return_reason" style={noMarginItemStyle}>
                  <Input.TextArea
                    variant="borderless"
                    placeholder="请输入退货原因"
                    autoSize={{ minRows: 7, maxRows: 7 }}
                  />
                </Form.Item>
                <div style={{ borderTop: '1px solid #1f1f1f', padding: '8px 12px' }}>
                  <div style={{ display: 'grid', gridTemplateColumns: '96px 1fr 88px 170px', gap: 8, alignItems: 'center' }}>
                    <span style={{ fontSize: 12, fontWeight: 600 }}>签名/日期</span>
                    <Form.Item name="applicant" style={noMarginItemStyle}>
                      {buildSelect('请选择申请人', contactOptions)}
                    </Form.Item>
                    <span style={{ fontSize: 12, textAlign: 'right' }}>日期</span>
                    <Form.Item name="application_date" style={noMarginItemStyle}>
                      <DatePicker style={{ width: '100%' }} format="YYYY-MM-DD" />
                    </Form.Item>
                  </div>
                </div>
              </td>
            </tr>

            <tr>
              <td style={labelCellStyle}>QA负责人意见</td>
              <td style={textAreaCellStyle} colSpan={6}>
                <Form.Item name="qa_head_opinion" style={noMarginItemStyle}>
                  <Input.TextArea
                    variant="borderless"
                    placeholder="请输入QA负责人意见"
                    autoSize={{ minRows: 5, maxRows: 5 }}
                  />
                </Form.Item>
                <div style={{ borderTop: '1px solid #1f1f1f', padding: '8px 12px' }}>
                  <div style={{ display: 'grid', gridTemplateColumns: '96px 1fr 88px 170px', gap: 8, alignItems: 'center' }}>
                    <span style={{ fontSize: 12, fontWeight: 600 }}>签名/日期</span>
                    <Form.Item name="qa_head" style={noMarginItemStyle}>
                      {buildSelect('请选择QA负责人', contactOptions)}
                    </Form.Item>
                    <span style={{ fontSize: 12, textAlign: 'right' }}>日期</span>
                    <Form.Item name="qa_head_date" style={noMarginItemStyle}>
                      <DatePicker style={{ width: '100%' }} format="YYYY-MM-DD" />
                    </Form.Item>
                  </div>
                </div>
              </td>
            </tr>

            <tr>
              <td style={labelCellStyle}>
                <div>质量管理负责人批准</div>
                <div>意见</div>
              </td>
              <td style={textAreaCellStyle} colSpan={6}>
                <div style={{ padding: '8px 12px 0', fontSize: 12 }}>
                  批准意见以填写内容为准
                </div>
                <Form.Item name="quality_manager_suggestion" style={noMarginItemStyle}>
                  <Input.TextArea
                    variant="borderless"
                    placeholder="请输入质量管理负责人建议"
                    autoSize={{ minRows: 4, maxRows: 4 }}
                  />
                </Form.Item>
                <div style={{ borderTop: '1px solid #1f1f1f', padding: '8px 12px' }}>
                  <div style={{ display: 'grid', gridTemplateColumns: '96px 1fr 88px 170px', gap: 8, alignItems: 'center' }}>
                    <span style={{ fontSize: 12, fontWeight: 600 }}>签名/日期</span>
                    <Form.Item name="quality_manager" style={noMarginItemStyle}>
                      {buildSelect('请选择质量管理负责人', contactOptions)}
                    </Form.Item>
                    <span style={{ fontSize: 12, textAlign: 'right' }}>日期</span>
                    <Form.Item name="quality_manager_date" style={noMarginItemStyle}>
                      <DatePicker style={{ width: '100%' }} format="YYYY-MM-DD" />
                    </Form.Item>
                  </div>
                </div>
              </td>
            </tr>

            <tr>
              <td style={labelCellStyle}>备注</td>
              <td style={textAreaCellStyle} colSpan={6}>
                <div style={{ padding: '8px 12px', fontSize: 12, color: '#595959' }}>
                  如需补充说明，可填写在上方右侧备注栏；此处保留为单据尾部说明区。
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </Form>
    </div>
  )
}
