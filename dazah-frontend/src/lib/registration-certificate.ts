export const registrationCertificateSheets = [
  {
    key: 'international-registration',
    name: '国外注册',
    path: '/registration/certificate-management/international-registration',
  },
  {
    key: 'domestic-registration',
    name: '国内注册',
    path: '/registration/certificate-management/domestic-registration',
  },
  {
    key: 'domestic-gmp',
    name: '国内GMP',
    path: '/registration/certificate-management/domestic-gmp',
  },
  {
    key: 'international-gmp',
    name: '国际GMP',
    path: '/registration/certificate-management/international-gmp',
  },
] as const

export type RegistrationCertificateSheetKey =
  (typeof registrationCertificateSheets)[number]['key']

export type RegistrationCertificateFieldKey =
  | 'certificate_name'
  | 'acceptance_number'
  | 'approval_number'
  | 'certificate_number'
  | 'issuing_authority'
  | 'issue_date'
  | 'validity_period'
  | 'product_scope'
  | 'quality_standard'
  | 'page_count'
  | 'remarks'

export interface RegistrationCertificateFieldConfig {
  key: RegistrationCertificateFieldKey
  label: string
  required?: boolean
  multiline?: boolean
  numeric?: boolean
}

export interface RegistrationCertificatePageColumnConfig {
  key: string
  label: string
  width: number
  type: 'sequence' | 'field' | 'blank'
}

export interface RegistrationCertificatePageLayoutConfig {
  columns: RegistrationCertificatePageColumnConfig[]
}

export const registrationCertificateSheetFields: Record<
  RegistrationCertificateSheetKey,
  RegistrationCertificateFieldConfig[]
> = {
  'international-registration': [
    { key: 'certificate_name', label: '证照名称', required: true },
    { key: 'certificate_number', label: '证书编号' },
    { key: 'issuing_authority', label: '国家/发证机关', multiline: true },
    { key: 'issue_date', label: '发证日期' },
    { key: 'validity_period', label: '有效期/复验期', multiline: true },
    { key: 'product_scope', label: '产品范围', multiline: true },
    { key: 'quality_standard', label: '质量标准', multiline: true },
    { key: 'page_count', label: '页数', numeric: true },
    { key: 'remarks', label: '备注', multiline: true },
  ],
  'domestic-registration': [
    { key: 'certificate_name', label: '证照名称', required: true },
    { key: 'acceptance_number', label: '受理号' },
    { key: 'approval_number', label: '批件号' },
    { key: 'certificate_number', label: '编号' },
    { key: 'issuing_authority', label: '发证机关', multiline: true },
    { key: 'issue_date', label: '发证日期' },
    { key: 'validity_period', label: '有效期/复验期', multiline: true },
    { key: 'product_scope', label: '产品范围', multiline: true },
    { key: 'quality_standard', label: '质量标准', multiline: true },
    { key: 'page_count', label: '页数', numeric: true },
    { key: 'remarks', label: '备注', multiline: true },
  ],
  'domestic-gmp': [
    { key: 'certificate_name', label: '证照名称', required: true },
    { key: 'certificate_number', label: '编号' },
    { key: 'issuing_authority', label: '发证机关', multiline: true },
    { key: 'issue_date', label: '发证日期' },
    { key: 'validity_period', label: '有效期/复验期', multiline: true },
    { key: 'product_scope', label: '产品范围', multiline: true },
    { key: 'quality_standard', label: '质量标准', multiline: true },
    { key: 'page_count', label: '页数', numeric: true },
    { key: 'remarks', label: '备注', multiline: true },
  ],
  'international-gmp': [
    { key: 'certificate_name', label: '证照名称', required: true },
    { key: 'certificate_number', label: '编号' },
    { key: 'issuing_authority', label: '国家/发证机关', multiline: true },
    { key: 'issue_date', label: '发证日期' },
    { key: 'validity_period', label: '有效期/复验期', multiline: true },
    { key: 'product_scope', label: '产品范围', multiline: true },
    { key: 'quality_standard', label: '质量标准', multiline: true },
    { key: 'page_count', label: '页数', numeric: true },
    { key: 'remarks', label: '备注', multiline: true },
  ],
}

export const registrationCertificatePageLayouts: Record<
  RegistrationCertificateSheetKey,
  RegistrationCertificatePageLayoutConfig
> = {
  'international-registration': {
    columns: [
      { key: 'sequence', label: '序号', width: 66, type: 'sequence' },
      { key: 'certificate_name', label: '证照名称', width: 222, type: 'field' },
      { key: 'certificate_number', label: '证书编号', width: 235, type: 'field' },
      { key: 'issuing_authority', label: '国家/发证机关', width: 215, type: 'field' },
      { key: 'issue_date', label: '发证日期', width: 149, type: 'field' },
      { key: 'validity_period', label: '有效期/复验期', width: 170, type: 'field' },
      { key: 'product_scope', label: '产品范围', width: 165, type: 'field' },
      { key: 'quality_standard', label: '质量标准', width: 160, type: 'field' },
      { key: 'page_count', label: '页数', width: 152, type: 'field' },
      { key: 'remarks', label: '备注', width: 279, type: 'field' },
      { key: 'blank_1', label: '', width: 90, type: 'blank' },
      { key: 'blank_2', label: '', width: 130, type: 'blank' },
    ],
  },
  'domestic-registration': {
    columns: [
      { key: 'sequence', label: '序号', width: 79, type: 'sequence' },
      { key: 'certificate_name', label: '证照名称', width: 214, type: 'field' },
      { key: 'acceptance_number', label: '受理号', width: 167, type: 'field' },
      { key: 'approval_number', label: '批件号', width: 166, type: 'field' },
      { key: 'certificate_number', label: '编号', width: 179, type: 'field' },
      { key: 'issuing_authority', label: '发证机关', width: 200, type: 'field' },
      { key: 'issue_date', label: '发证日期', width: 107, type: 'field' },
      { key: 'validity_period', label: '有效期/复验期', width: 187, type: 'field' },
      { key: 'product_scope', label: '产品范围', width: 176, type: 'field' },
      { key: 'quality_standard', label: '质量标准', width: 222, type: 'field' },
      { key: 'page_count', label: '页数', width: 91, type: 'field' },
      { key: 'remarks', label: '备注', width: 146, type: 'field' },
    ],
  },
  'domestic-gmp': {
    columns: [
      { key: 'sequence', label: '序号', width: 70, type: 'sequence' },
      { key: 'certificate_name', label: '证照名称', width: 145, type: 'field' },
      { key: 'certificate_number', label: '编号', width: 224, type: 'field' },
      { key: 'issuing_authority', label: '发证机关', width: 170, type: 'field' },
      { key: 'issue_date', label: '发证日期', width: 151, type: 'field' },
      { key: 'validity_period', label: '有效期/复验期', width: 149, type: 'field' },
      { key: 'product_scope', label: '产品范围', width: 216, type: 'field' },
      { key: 'quality_standard', label: '质量标准', width: 290, type: 'field' },
      { key: 'page_count', label: '页数', width: 97, type: 'field' },
      { key: 'remarks', label: '备注', width: 160, type: 'field' },
      { key: 'blank_1', label: '', width: 121, type: 'blank' },
      { key: 'blank_2', label: '', width: 90, type: 'blank' },
    ],
  },
  'international-gmp': {
    columns: [
      { key: 'sequence', label: '序号', width: 90, type: 'sequence' },
      { key: 'certificate_name', label: '证照名称', width: 149, type: 'field' },
      { key: 'certificate_number', label: '编号', width: 207, type: 'field' },
      { key: 'issuing_authority', label: '国家/发证机关', width: 200, type: 'field' },
      { key: 'issue_date', label: '发证日期', width: 187, type: 'field' },
      { key: 'validity_period', label: '有效期/复验期', width: 194, type: 'field' },
      { key: 'product_scope', label: '产品范围', width: 217, type: 'field' },
      { key: 'quality_standard', label: '质量标准', width: 189, type: 'field' },
      { key: 'page_count', label: '页数', width: 170, type: 'field' },
      { key: 'remarks', label: '备注', width: 287, type: 'field' },
      { key: 'blank_1', label: '', width: 90, type: 'blank' },
      { key: 'blank_2', label: '', width: 130, type: 'blank' },
    ],
  },
}

export function isRegistrationCertificateSheetKey(
  value: string
): value is RegistrationCertificateSheetKey {
  return registrationCertificateSheets.some((sheet) => sheet.key === value)
}

export function getRegistrationCertificateSheetName(
  key: RegistrationCertificateSheetKey
): string {
  return registrationCertificateSheets.find((sheet) => sheet.key === key)?.name || key
}
