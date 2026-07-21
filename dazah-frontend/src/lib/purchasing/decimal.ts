type DecimalInput = string | number | null | undefined

type ParsedDecimal = {
  sign: bigint
  integer: string
  fraction: string
}

const ZERO = BigInt(0)
const ONE = BigInt(1)
const NEGATIVE_ONE = BigInt(-1)

function parseDecimal(value: DecimalInput): ParsedDecimal | null {
  if (value === null || value === undefined || value === '') return null

  const normalized = String(value).replace(/[¥￥,\s]/g, '')
  const match = normalized.match(/^(-?)(\d+)(?:\.(\d+))?$/)
  if (!match) return null

  return {
    sign: match[1] === '-' ? NEGATIVE_ONE : ONE,
    integer: match[2],
    fraction: match[3] ?? '',
  }
}

function decimalToScaledInt(value: DecimalInput, scale: number): bigint {
  const parsed = parseDecimal(value)
  if (!parsed) return ZERO

  const fraction = parsed.fraction.padEnd(scale, '0').slice(0, scale)
  return parsed.sign * BigInt(`${parsed.integer}${fraction || ''}`)
}

function maxFractionLength(values: DecimalInput[], fallbackScale: number) {
  return values.reduce<number>((maxScale, value) => {
    const parsed = parseDecimal(value)
    if (!parsed) return maxScale
    return Math.max(maxScale, parsed.fraction.length)
  }, fallbackScale)
}

function formatScaledInt(value: bigint, scale: number, options?: { trim?: boolean }) {
  const sign = value < ZERO ? '-' : ''
  const absoluteText = (value < ZERO ? -value : value).toString().padStart(scale + 1, '0')
  const integer = scale > 0 ? absoluteText.slice(0, -scale) || '0' : absoluteText
  const fraction = scale > 0 ? absoluteText.slice(-scale) : ''
  const text = scale > 0 ? `${sign}${integer}.${fraction}` : `${sign}${integer}`

  if (!options?.trim) return text

  const trimmed = text.replace(/\.?0+$/, '')
  return trimmed === '' || trimmed === '-' ? '0' : trimmed
}

export function sumMoney(values: DecimalInput[]) {
  const total = values.reduce<bigint>(
    (sum, value) => sum + decimalToScaledInt(value, 2),
    ZERO
  )
  return `¥${formatScaledInt(total, 2)}`
}

export function sumQuantity(values: DecimalInput[]) {
  const scale = maxFractionLength(values, 0)
  const total = values.reduce<bigint>(
    (sum, value) => sum + decimalToScaledInt(value, scale),
    ZERO
  )
  return formatScaledInt(total, scale, { trim: true })
}

export function isPresentDecimal(value: DecimalInput) {
  return parseDecimal(value) !== null
}
