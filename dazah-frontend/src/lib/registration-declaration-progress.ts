export const registrationDeclarationProgressSheets = [
  {
    key: 'international-planned-in-progress',
    name: '2026国际注册（计划和进行中）项目',
    path: '/registration/declaration-progress/international-planned-in-progress',
  },
  {
    key: 'domestic-planned-in-progress',
    name: '2026年国内注册（计划和进行中）项目',
    path: '/registration/declaration-progress/domestic-planned-in-progress',
  },
  {
    key: 'new-product-projects',
    name: '2026年新产品项目',
    path: '/registration/declaration-progress/new-product-projects',
  },
  {
    key: 'international-completed',
    name: '2026年国际注册（已完成）',
    path: '/registration/declaration-progress/international-completed',
  },
  {
    key: 'domestic-completed',
    name: '2026年国内注册（已完成）',
    path: '/registration/declaration-progress/domestic-completed',
  },
  {
    key: 'gmp-projects',
    name: '2026年GMP项目',
    path: '/registration/declaration-progress/gmp-projects',
  },
  {
    key: 'us-fda-progress',
    name: '美国FDA注册进展',
    path: '/registration/declaration-progress/us-fda-progress',
  },
] as const

export type RegistrationDeclarationProgressSheetKey =
  (typeof registrationDeclarationProgressSheets)[number]['key']

export function isRegistrationDeclarationProgressSheetKey(
  value: string
): value is RegistrationDeclarationProgressSheetKey {
  return registrationDeclarationProgressSheets.some((sheet) => sheet.key === value)
}
