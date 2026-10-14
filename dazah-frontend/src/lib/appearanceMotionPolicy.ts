export type AppearanceMotion = 'reveal' | 'fade' | 'none'

/** Hardware hints are conservative; actual capture and frame costs decide further degradation. */
export function createAppearanceMotionPolicy() {
  let degradedUntil = 0
  let degraded: AppearanceMotion = 'fade'
  let slowFrames = 0
  const degrade = (motion: AppearanceMotion, now: number) => {
    degraded = motion
    degradedUntil = now + 60_000
  }
  return {
    choose(hardware: { cores?: number; memory?: number }, now: number): AppearanceMotion {
      if (now < degradedUntil) return degraded
      if ((hardware.cores !== undefined && hardware.cores > 0 && hardware.cores <= 2) ||
        (hardware.memory !== undefined && hardware.memory > 0 && hardware.memory <= 2)) return 'fade'
      return 'reveal'
    },
    capture(duration: number, now: number) {
      if (duration >= 400) degrade('none', now)
      else if (duration >= 120) degrade('fade', now)
    },
    begin() { slowFrames = 0 },
    frame(interval: number, now: number): boolean {
      slowFrames = interval >= 40 ? slowFrames + 1 : 0
      if (slowFrames < 2) return false
      degrade(interval >= 100 ? 'none' : 'fade', now)
      return true
    },
  }
}
