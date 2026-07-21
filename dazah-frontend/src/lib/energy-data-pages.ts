export const ENERGY_DATA_PAGES = [
  { key: 'daily-total', label: '日总量', slug: 'daily-total', pageKey: 'energy.daily_total' },
  { key: 'electricity', label: '电量', slug: 'electricity', pageKey: 'energy.electricity' },
  { key: 'drinking-water', label: '饮用水量', slug: 'drinking-water', pageKey: 'energy.drinking_water' },
  { key: 'steam', label: '蒸汽量', slug: 'steam', pageKey: 'energy.steam' },
  { key: 'chilled-water', label: '冰水量', slug: 'chilled-water', pageKey: 'energy.chilled_water' },
  { key: 'air', label: '空气量', slug: 'air', pageKey: 'energy.air' },
  { key: 'circulating-water', label: '循环水量', slug: 'circulating-water', pageKey: 'energy.circulating_water' },
  { key: 'workshop-energy-detail', label: '车间能源详情', slug: 'workshop-energy-detail', pageKey: 'energy.workshop_detail' },
] as const

export type EnergyDataPage = (typeof ENERGY_DATA_PAGES)[number]

export function getEnergyDataPage(slug: string): EnergyDataPage | undefined {
  return ENERGY_DATA_PAGES.find((page) => page.slug === slug)
}
