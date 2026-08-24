import { afterEach, describe, expect, it } from 'vitest'

import { useAuthStore } from './auth'

describe('authentication display store', () => {
  afterEach(() => useAuthStore.getState().clearUser())

  it('only reports explicitly granted permissions or the wildcard', () => {
    useAuthStore.getState().setUser({
      id: 'user-1',
      name: '管理员',
      permissions: ['quality.read'],
    })

    expect(useAuthStore.getState().hasPermission('quality.read')).toBe(true)
    expect(useAuthStore.getState().hasPermission('quality.write')).toBe(false)

    useAuthStore.getState().setUser({
      id: 'user-2',
      name: '超级管理员',
      permissions: ['*'],
    })
    expect(useAuthStore.getState().hasPermission('quality.write')).toBe(true)
  })
})
