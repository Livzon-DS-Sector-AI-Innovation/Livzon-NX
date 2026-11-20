import { useEffect, useEffectEvent, useState, type ChangeEvent, type CompositionEvent } from 'react'

export const SEARCH_DELAY_MS = 250

export function useSearchFilter(keyword: string, onSearch: (value: string) => void) {
  const [searchText, setSearchText] = useState(keyword)
  const [composing, setComposing] = useState(false)
  const nextKeyword = searchText.trim()
  const searchPending = nextKeyword !== keyword
  const applySearch = useEffectEvent(onSearch)

  useEffect(() => {
    if (!searchPending || composing) return
    const timer = window.setTimeout(() => applySearch(nextKeyword), nextKeyword ? SEARCH_DELAY_MS : 0)
    return () => window.clearTimeout(timer)
  }, [composing, nextKeyword, searchPending])

  return {
    searchPending,
    setSearchText,
    inputProps: {
      value: searchText,
      onChange: (event: ChangeEvent<HTMLInputElement>) => setSearchText(event.target.value),
      onCompositionStart: () => setComposing(true),
      onCompositionEnd: (event: CompositionEvent<HTMLInputElement>) => {
        setSearchText(event.currentTarget.value)
        setComposing(false)
      },
    },
  }
}
