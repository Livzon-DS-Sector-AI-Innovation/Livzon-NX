import { flushSync } from 'react-dom'
import { createAppearanceMotionPolicy } from './appearanceMotionPolicy'

interface ActiveAppearanceTransition {
  transition: ViewTransition
  animation?: Animation
  stopMonitoring?: () => void
}

let activeTransition: ActiveAppearanceTransition | undefined
const motionPolicy = createAppearanceMotionPolicy()

/** Reveal the new palette from the button's lower left toward the viewport's upper right. */
export function transitionAppearance(button: Element, update: () => void, colorChanged: boolean) {
  activeTransition?.stopMonitoring?.()
  activeTransition?.animation?.cancel()
  activeTransition?.transition.skipTransition()
  activeTransition = undefined
  const root = document.documentElement
  const clearStyles = () => {
    delete root.dataset.appearanceTransition
    root.style.removeProperty('--appearance-reveal-x')
    root.style.removeProperty('--appearance-reveal-y')
  }
  const hardware = {
    cores: navigator.hardwareConcurrency,
    memory: 'deviceMemory' in navigator && typeof navigator.deviceMemory === 'number' ? navigator.deviceMemory : undefined,
  }
  const motion = motionPolicy.choose(hardware, performance.now())
  if (!colorChanged || motion === 'none' || !document.startViewTransition ||
    window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    clearStyles()
    update()
    return
  }

  const { left, bottom } = button.getBoundingClientRect()
  const radius = Math.hypot(window.innerWidth, window.innerHeight)
  root.style.setProperty('--appearance-reveal-x', `${left}px`)
  root.style.setProperty('--appearance-reveal-y', `${bottom}px`)
  root.dataset.appearanceTransition = motion === 'fade' ? 'fade' : 'active'
  let applied = false
  const apply = () => {
    if (applied) return
    applied = true
    flushSync(update)
  }
  try {
    const captureStarted = performance.now()
    const transition = document.startViewTransition(apply)
    const active: ActiveAppearanceTransition = { transition }
    activeTransition = active
    void transition.ready.then(() => {
      // A superseded capture must not start another full-screen animation.
      if (activeTransition !== active) return
      motionPolicy.capture(performance.now() - captureStarted, performance.now())
      const currentMotion = motionPolicy.choose(hardware, performance.now())
      if (currentMotion === 'none') { transition.skipTransition(); return }
      root.dataset.appearanceTransition = currentMotion === 'fade' ? 'fade' : 'active'
      const keyframes = currentMotion === 'fade' ? { opacity: [0, 1] } : { clipPath: [
        `circle(0px at ${left}px ${bottom}px)`,
        `circle(${radius}px at ${window.innerWidth}px 0px)`,
      ] }
      active.animation = root.animate(keyframes, {
        duration: currentMotion === 'fade' ? 160 : 480,
        fill: 'both',
        easing: 'cubic-bezier(0.4, 0, 0.2, 1)',
        pseudoElement: '::view-transition-new(root)',
      })
      // Only sample while the animation runs; hidden tabs and superseded captures are ignored.
      motionPolicy.begin()
      let previous: number | undefined
      let frame = 0
      const sample = (now: number) => {
        if (activeTransition !== active || document.hidden) return
        if (previous !== undefined && motionPolicy.frame(now - previous, now)) {
          active.animation?.cancel()
          transition.skipTransition()
          return
        }
        previous = now
        frame = requestAnimationFrame(sample)
      }
      frame = requestAnimationFrame(sample)
      active.stopMonitoring = () => cancelAnimationFrame(frame)
    }).catch(() => { transition.skipTransition() })
    const cleanup = () => {
      // Filled animations otherwise retain their effect after the transition disappears.
      active.stopMonitoring?.()
      active.animation?.cancel()
      if (activeTransition !== active) return
      activeTransition = undefined
      clearStyles()
    }
    void transition.finished.then(cleanup, cleanup)
  } catch {
    activeTransition = undefined
    clearStyles()
    apply()
  }
}
