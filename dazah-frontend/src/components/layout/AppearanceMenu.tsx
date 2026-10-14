'use client'

import { Radio } from 'antd'
import { DesktopOutlined, MoonOutlined, SunOutlined } from '@ant-design/icons'
import { useAppearance } from '@/lib/useAppearance'
import { DARK_MODE_QUERY, parseAppearance, resolveAppearance } from '@/lib/appearance'
import { transitionAppearance } from '@/lib/appearanceTransition'

export function AppearanceMenu({ vertical = false }: { vertical?: boolean }) {
  const { mode, resolved, setAppearance } = useAppearance()
  return <Radio.Group aria-label="外观模式" value={mode} size="small"
    className={vertical ? 'appearance-switch appearance-switch-vertical' : 'appearance-switch'}
    onChange={(event) => {
      const next = parseAppearance(event.target.value)
      const input = event.nativeEvent.target
      const button = input instanceof Element ? input.closest('.ant-radio-button-wrapper') : null
      if (!button) { setAppearance(next); return }
      transitionAppearance(button, () => setAppearance(next),
        resolveAppearance(next, window.matchMedia(DARK_MODE_QUERY).matches) !== resolved)
    }}>
    <Radio.Button value="light" aria-label="浅色" title="浅色"><SunOutlined aria-hidden /></Radio.Button>
    <Radio.Button value="dark" aria-label="深色" title="深色"><MoonOutlined aria-hidden /></Radio.Button>
    <Radio.Button value="system" aria-label="跟随系统" title="跟随系统"><DesktopOutlined aria-hidden /></Radio.Button>
  </Radio.Group>
}
