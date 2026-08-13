import dayjs from 'dayjs'
import { describe, expect, it } from 'vitest'
import { buildUrgentPurchasePayload } from './UrgentPurchaseRequestFormClient'

describe('urgent purchase request form', () => {
  it('flattens category groups and keeps the attachment note', () => {
    const payload = buildUrgentPurchasePayload({
      request_department: '采购部',
      request_date: dayjs('2026-08-12'),
      attachment_note: '加急技术附件',
      groups: [
        {
          category: 'fire',
          items: [
            {
              product_name: '',
              specification: '',
              material_code: 'FIRE-001',
              material_description: '灭火器',
              rule_model: '4kg',
              purpose: '消防补充',
              material: '',
              brand: '',
              quantity: 1,
              unit: '具',
              unit_price: 50,
              remarks: '急用',
            },
          ],
        },
        {
          category: 'office',
          items: [
            {
              product_name: '标签纸',
              specification: 'A4',
              material_code: '',
              material_description: '',
              rule_model: '',
              purpose: '',
              material: '',
              brand: '',
              quantity: 2,
              unit: '包',
              unit_price: 5,
              remarks: '',
            },
          ],
        },
      ],
    })

    expect(payload.category).toBe('urgent')
    expect(payload.request_date).toBe('2026-08-12')
    expect(payload.attachment_note).toBe('加急技术附件')
    expect(payload.items.map((item) => item.item_category)).toEqual(['fire', 'office'])
  })
})
