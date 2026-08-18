'use client'

import type { ComponentProps } from 'react'
import { Input } from 'antd'

type AntInputProps = ComponentProps<typeof Input>

export type PurchaseDetailInputSizing = {
  minWidth: number
  maxWidth: number
}

export const purchaseDetailInputSizing = {
  materialCode: { minWidth: 150, maxWidth: 280 },
  materialDescription: { minWidth: 180, maxWidth: 320 },
  ruleModel: { minWidth: 150, maxWidth: 280 },
  productName: { minWidth: 160, maxWidth: 300 },
  specification: { minWidth: 130, maxWidth: 280 },
  purpose: { minWidth: 160, maxWidth: 360 },
  material: { minWidth: 110, maxWidth: 220 },
  brand: { minWidth: 110, maxWidth: 220 },
  unit: { minWidth: 90, maxWidth: 150 },
  remarks: { minWidth: 180, maxWidth: 360 },
} as const satisfies Record<string, PurchaseDetailInputSizing>

const INPUT_HORIZONTAL_PADDING = 32
export const PURCHASE_DETAIL_TABLE_CELL_HORIZONTAL_PADDING = 24
const NARROW_CHARACTER_WIDTH = 8
const WIDE_CHARACTER_WIDTH = 14

function estimateTextWidth(value: unknown) {
  const text = String(value ?? '')
  const longestLine = text.split(/\r?\n/).reduce((longest, line) => {
    const lineWidth = Array.from(line).reduce(
      (width, character) =>
        width +
        (character === '\t'
          ? NARROW_CHARACTER_WIDTH * 4
          : character.charCodeAt(0) > 255
            ? WIDE_CHARACTER_WIDTH
            : NARROW_CHARACTER_WIDTH),
      0,
    )
    return Math.max(longest, lineWidth)
  }, 0)

  return longestLine
}

export function getPurchaseDetailInputWidth(
  value: unknown,
  sizing: PurchaseDetailInputSizing,
) {
  const minWidth = Math.max(0, sizing.minWidth)
  const maxWidth = Math.max(minWidth, sizing.maxWidth)
  const contentWidth = Math.ceil(estimateTextWidth(value) + INPUT_HORIZONTAL_PADDING)
  return Math.min(maxWidth, Math.max(minWidth, contentWidth))
}

export function getPurchaseDetailColumnWidth(
  values: ReadonlyArray<unknown>,
  field: string,
  sizing: PurchaseDetailInputSizing,
) {
  return values.reduce<number>((width, item) => {
    const value = item && typeof item === 'object'
      ? (item as Record<string, unknown>)[field]
      : undefined
    return Math.max(
      width,
      getPurchaseDetailInputWidth(value, sizing) +
        PURCHASE_DETAIL_TABLE_CELL_HORIZONTAL_PADDING,
    )
  }, sizing.minWidth + PURCHASE_DETAIL_TABLE_CELL_HORIZONTAL_PADDING)
}

export type PurchaseDetailAutoInputProps = Omit<AntInputProps, 'value'> & {
  value?: AntInputProps['value']
  minWidth?: number
  maxWidth?: number
}

export function PurchaseDetailAutoInput({
  value,
  minWidth = purchaseDetailInputSizing.productName.minWidth,
  maxWidth = purchaseDetailInputSizing.productName.maxWidth,
  style,
  title,
  ...props
}: PurchaseDetailAutoInputProps) {
  const width = getPurchaseDetailInputWidth(value, { minWidth, maxWidth })
  const textValue = String(value ?? '')

  return (
    <Input
      {...props}
      value={value}
      title={title ?? (textValue || undefined)}
      style={{ ...style, width, minWidth, maxWidth }}
    />
  )
}
