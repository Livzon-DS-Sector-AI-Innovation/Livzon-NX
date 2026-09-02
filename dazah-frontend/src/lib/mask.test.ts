import { describe, expect, it } from 'vitest'

import { maskBankAccount, maskIdCard, maskMiddle, maskPhone } from './mask'

describe('maskPhone', () => {
  it('keeps 3 head 4 tail', () => {
    expect(maskPhone('13800131234')).toBe('138****1234')
  })
  it('returns short values untouched and empty as dash', () => {
    expect(maskPhone('1234567')).toBe('1234567')
    expect(maskPhone('')).toBe('-')
    expect(maskPhone(null)).toBe('-')
    expect(maskPhone(undefined)).toBe('-')
  })
})

describe('maskIdCard', () => {
  it('keeps 6 head 4 tail with stars between', () => {
    expect(maskIdCard('110101199001011234')).toBe('110101********1234')
  })
  it('short ids are untouched', () => {
    expect(maskIdCard('1234567890')).toBe('1234567890')
    expect(maskIdCard('')).toBe('-')
  })
})

describe('maskBankAccount', () => {
  it('keeps only last 4', () => {
    expect(maskBankAccount('6222020200112233445')).toBe('****3445')
  })
  it('short or empty values', () => {
    expect(maskBankAccount('1234567')).toBe('1234567')
    expect(maskBankAccount(null)).toBe('-')
  })
})

describe('maskMiddle', () => {
  it('masks middle with capped stars', () => {
    // 默认 keepTail=0：不得回显原文（slice(-0) 陷阱回归），head 保留 4 字
    expect(maskMiddle('北京市海淀区中关村大街1号', 4)).toBe('北京市海******')
    // 星号数量封顶 6
    expect(maskMiddle('a'.repeat(30), 2)).toBe('aa******')
  })
  it('values within keep budget stay untouched', () => {
    expect(maskMiddle('abc', 4, 2)).toBe('abc')
    expect(maskMiddle('')).toBe('-')
  })
  it('supports tail keeping', () => {
    expect(maskMiddle('13800131234', 0, 4)).toBe('******1234')
    expect(maskMiddle('13800131234', 3, 4)).toBe('138****1234')
  })
})
