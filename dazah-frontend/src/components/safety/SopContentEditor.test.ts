import { describe, expect, it } from 'vitest'

import { isSopTableChapter } from './SopContentEditor.logic'

describe('isSopTableChapter', () => {
  it('routes only structured table chapters to the table renderer', () => {
    expect([1, 2, 6, 7, 9].filter(isSopTableChapter)).toEqual([])
    expect([3, 4, 5, 8].every(isSopTableChapter)).toBe(true)
  })
})
