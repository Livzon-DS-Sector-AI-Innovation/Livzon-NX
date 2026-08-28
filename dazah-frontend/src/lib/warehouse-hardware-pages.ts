export interface WarehouseHardwarePageDefinition {
  slug: string
  label: string
  pageKey: string
  path: string
}

export const warehouseHardwarePages: WarehouseHardwarePageDefinition[] = [
  { slug: 'summary', label: '五金', pageKey: 'hardware-summary', path: '/warehouse/hardware/summary' },
  { slug: 'electrical', label: '电仪', pageKey: 'hardware-electrical', path: '/warehouse/hardware/electrical' },
  { slug: '101-1-workshop', label: '101-1车间', pageKey: 'hardware-101-1-workshop', path: '/warehouse/hardware/101-1-workshop' },
  { slug: '101-2-workshop', label: '101-2车间', pageKey: 'hardware-101-2-workshop', path: '/warehouse/hardware/101-2-workshop' },
  { slug: '102-workshop', label: '102车间', pageKey: 'hardware-102-workshop', path: '/warehouse/hardware/102-workshop' },
  { slug: '103-workshop', label: '103车间', pageKey: 'hardware-103-workshop', path: '/warehouse/hardware/103-workshop' },
  { slug: '201-1-workshop', label: '201-1车间', pageKey: 'hardware-201-1-workshop', path: '/warehouse/hardware/201-1-workshop' },
  { slug: '201-2-workshop', label: '201-2车间', pageKey: 'hardware-201-2-workshop', path: '/warehouse/hardware/201-2-workshop' },
  { slug: '201-3-workshop', label: '201-3车间', pageKey: 'hardware-201-3-workshop', path: '/warehouse/hardware/201-3-workshop' },
  { slug: '202-workshop', label: '202车间', pageKey: 'hardware-202-workshop', path: '/warehouse/hardware/202-workshop' },
  { slug: '203-workshop', label: '203车间', pageKey: 'hardware-203-workshop', path: '/warehouse/hardware/203-workshop' },
  { slug: '203-3-workshop', label: '203-3车间', pageKey: 'hardware-203-3-workshop', path: '/warehouse/hardware/203-3-workshop' },
  { slug: 'thermal-station', label: '热动站', pageKey: 'hardware-thermal-station', path: '/warehouse/hardware/thermal-station' },
  { slug: 'power-department', label: '动力部', pageKey: 'hardware-power-department', path: '/warehouse/hardware/power-department' },
  { slug: 'wastewater', label: '污水处理', pageKey: 'hardware-wastewater', path: '/warehouse/hardware/wastewater' },
  { slug: 'warehouse', label: '仓库', pageKey: 'hardware-warehouse', path: '/warehouse/hardware/warehouse' },
  { slug: 'rd-center', label: '研发中心', pageKey: 'hardware-rd-center', path: '/warehouse/hardware/rd-center' },
  { slug: 'others', label: '其它', pageKey: 'hardware-others', path: '/warehouse/hardware/others' },
  { slug: 'inbound-ledger', label: '入库记录', pageKey: 'hardware-inbound-ledger', path: '/warehouse/hardware/inbound-ledger' },
  { slug: 'outbound-ledger', label: '出库记录', pageKey: 'hardware-outbound-ledger', path: '/warehouse/hardware/outbound-ledger' },
]

export const warehouseHardwarePageMap = new Map(
  warehouseHardwarePages.map((item) => [item.slug, item])
)
