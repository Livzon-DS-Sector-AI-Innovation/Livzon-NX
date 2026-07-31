const TABLE_CHAPTER_IDS = new Set([3, 4, 5, 8])

export function isSopTableChapter(chapterId: number): boolean {
  return TABLE_CHAPTER_IDS.has(chapterId)
}
