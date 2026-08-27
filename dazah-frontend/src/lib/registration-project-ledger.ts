export const registrationProjectLedgerSheets = [
  {
    key: 'international-associated-review',
    name: '国际注册（关联审评机制）',
    path: '/registration/project-ledger/international-associated-review',
  },
  {
    key: 'international-standalone-review',
    name: '国际注册（原料药单独审评机制）',
    path: '/registration/project-ledger/international-standalone-review',
  },
  {
    key: 'domestic-associated-review',
    name: '国内注册（关联审评机制）',
    path: '/registration/project-ledger/domestic-associated-review',
  },
  {
    key: 'domestic-standalone-review',
    name: '国内注册（原料药单独审评机制）',
    path: '/registration/project-ledger/domestic-standalone-review',
  },
] as const

export type RegistrationProjectLedgerSheetKey =
  (typeof registrationProjectLedgerSheets)[number]['key']

export function isRegistrationProjectLedgerSheetKey(
  value: string
): value is RegistrationProjectLedgerSheetKey {
  return registrationProjectLedgerSheets.some((sheet) => sheet.key === value)
}
