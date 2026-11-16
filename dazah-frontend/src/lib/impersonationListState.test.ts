/* @vitest-environment happy-dom */

import { afterEach, expect, it, vi } from 'vitest'
import {
  finishImpersonationListReturn,
  saveImpersonationListState,
  takeRestoredImpersonationListState,
} from './impersonationListState'

const filters = { keyword: '采购', roleId: 'reader', page: 3 }

afterEach(() => {
  vi.unstubAllGlobals()
  sessionStorage.clear()
})

it('consumes the filters once after the administrator session is restored', () => {
  saveImpersonationListState(filters)
  expect(takeRestoredImpersonationListState()).toBeUndefined()
  finishImpersonationListReturn(true)
  expect(takeRestoredImpersonationListState()).toEqual(filters)
  expect(takeRestoredImpersonationListState()).toBeUndefined()
})

it('discards saved filters when the administrator must log in again', () => {
  saveImpersonationListState(filters)
  finishImpersonationListReturn(false)
  finishImpersonationListReturn(true)
  expect(takeRestoredImpersonationListState()).toBeUndefined()
})

it('allows switching and returning when browser storage is blocked', () => {
  vi.stubGlobal('sessionStorage', {
    getItem: () => { throw new Error('Storage blocked') },
    setItem: () => { throw new Error('Storage blocked') },
  })
  expect(() => saveImpersonationListState(filters)).not.toThrow()
  expect(() => finishImpersonationListReturn(true)).not.toThrow()
  expect(takeRestoredImpersonationListState()).toBeUndefined()
})
