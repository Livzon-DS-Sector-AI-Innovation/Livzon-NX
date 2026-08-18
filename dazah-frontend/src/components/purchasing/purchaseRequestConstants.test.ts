import { describe, expect, it } from 'vitest'
import {
  approvalRoleHints,
  approvalRoleLabels,
  approvalRoleRequiredApprovals,
  approvalRoleToStep,
  approvalStepToRole,
  calculateGroupsTotal,
  calculateItemsTotal,
  defaultPurchaseRequestItem,
  normalPurchaseCategories,
  purchaseApprovalWorkflows,
  purchaseCategoryLabels,
  purchaseStatusLabels,
  usesMaterialFields,
} from './purchaseRequestConstants'

describe('purchase request category fields', () => {
  it('exposes the expanded categories and material-field rules', () => {
    expect(purchaseCategoryLabels).toMatchObject({
      'advertising-printing': '广告/印刷',
      fire: '消防',
      packaging: '包材',
      'labor-special': '特防',
      'labor-miscellaneous': '杂品',
      urgent: '加急单',
    })
    expect('labor-protection' in purchaseCategoryLabels).toBe(false)

    expect(usesMaterialFields('hardware')).toBe(true)
    expect(usesMaterialFields('fire')).toBe(true)
    expect(usesMaterialFields('labor-special')).toBe(true)
    expect(usesMaterialFields('advertising-printing')).toBe(false)
    expect(usesMaterialFields('office')).toBe(false)
    expect(normalPurchaseCategories).not.toContain('urgent')
  })

  it('initializes the new item fields as empty values', () => {
    expect(defaultPurchaseRequestItem).toMatchObject({
      material_code: '',
      material_description: '',
      rule_model: '',
    })
  })

  it('calculates each group subtotal and the total across groups', () => {
    expect(calculateItemsTotal([
      { quantity: '23.0000', unit_price: '123.0000' },
      { quantity: 2, unit_price: 5 },
    ])).toBe(2839)
    expect(calculateGroupsTotal([
      { items: [{ quantity: 23, unit_price: 123 }] },
      { items: [{ quantity: '2', unit_price: '5.00' }] },
    ])).toBe(2839)
  })

  it('defines the category-specific approval workflows and labels', () => {
    expect(purchaseApprovalWorkflows).toEqual({
      hardware: [
        'hardware_warehouse',
        'department_head',
        'responsible_leader',
        'supervising_leader',
        'general_manager',
      ],
      electrical: [
        'hardware_warehouse',
        'equipment_power',
        'department_head',
        'responsible_leader',
        'supervising_leader',
      ],
      'labor-special': [
        'safety_officer',
        'department_head',
        'responsible_leader',
      ],
      urgent: [
        'hardware_warehouse',
        'department_head',
        'responsible_leader',
        'supervising_leader',
        'finance_director',
        'general_manager',
      ],
      computer: ['department_head', 'responsible_leader', 'supervising_leader'],
      office: ['department_head', 'responsible_leader', 'supervising_leader'],
      'raw-auxiliary': ['department_head', 'responsible_leader', 'supervising_leader'],
      'chemical-glass': ['department_head', 'responsible_leader', 'supervising_leader'],
      'advertising-printing': [
        'department_head',
        'responsible_leader',
        'supervising_leader',
      ],
      fire: ['department_head', 'responsible_leader', 'supervising_leader'],
      packaging: ['department_head', 'responsible_leader', 'supervising_leader'],
      'labor-miscellaneous': [
        'department_head',
        'responsible_leader',
        'supervising_leader',
      ],
    })
    expect(approvalRoleLabels).toMatchObject({
      hardware_warehouse: '五金库',
      equipment_power: '设备动力部（何学斌、安伟）',
      safety_officer: '安全员',
      supervising_leader: '主管领导',
      finance_director: '财务总监',
      general_manager: '总经理',
    })
    expect(approvalRoleRequiredApprovals.equipment_power).toBe(2)
    expect(approvalRoleHints.equipment_power).toContain('何学斌、安伟')
    expect(approvalStepToRole['equipment-power']).toBe('equipment_power')
    expect(approvalRoleToStep.equipment_power).toBe('equipment-power')
    expect(purchaseStatusLabels.pending_equipment_power).toBe('待设备动力部审批')
    expect(purchaseStatusLabels.pending_general_manager).toBe('待总经理审批')
  })
})
