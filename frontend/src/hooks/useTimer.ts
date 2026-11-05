import { useEffect, useRef, useState, useCallback } from 'react'

/**
 * Server-authoritative countdown timer.
 * Counts down from deadlineAt (ISO string). Recalculates on each tick
 * to protect against tab sleep.
 *
 * Supports pause: when paused, the countdown stops and the remaining
 * time is frozen. On resume, the internal deadline is shifted forward
 * by the paused duration so the remaining time picks up where it left off.
 */
export function useTimer(
  deadlineAt: string | null | undefined,
  onExpire: () => void,
) {
  const [secondsLeft, setSecondsLeft] = useState<number | null>(null)
  const [paused, setPaused] = useState(false)
  const expiredRef = useRef(false)
  const onExpireRef = useRef(onExpire)
  onExpireRef.current = onExpire
  const deadlineRef = useRef<number | null>(null)
  const pausedAtRef = useRef<number | null>(null)

  // Keep deadlineRef in sync with prop
  useEffect(() => {
    if (deadlineAt) {
      deadlineRef.current = new Date(deadlineAt).getTime()
    } else {
      deadlineRef.current = null
    }
  }, [deadlineAt])

  const recompute = useCallback(() => {
    if (!deadlineRef.current) return null
    const diff = Math.floor((deadlineRef.current - Date.now()) / 1000)
    return Math.max(0, diff)
  }, [])

  useEffect(() => {
    if (!deadlineAt) return
    expiredRef.current = false
    setSecondsLeft(recompute())

    const interval = setInterval(() => {
      if (paused) return
      const secs = recompute()
      setSecondsLeft(secs)
      if (secs !== null && secs <= 0 && !expiredRef.current) {
        expiredRef.current = true
        onExpireRef.current()
      }
    }, 1000)

    return () => clearInterval(interval)
  }, [deadlineAt, recompute, paused])

  // When un-pausing, shift the deadline forward by the paused duration
  useEffect(() => {
    if (!paused && pausedAtRef.current !== null && deadlineRef.current) {
      const pauseDuration = Date.now() - pausedAtRef.current
      deadlineRef.current += pauseDuration
      pausedAtRef.current = null
      setSecondsLeft(recompute())
    }
    if (paused && pausedAtRef.current === null) {
      pausedAtRef.current = Date.now()
    }
  }, [paused, recompute])

  const togglePause = useCallback(() => setPaused(p => !p), [])

  return { secondsLeft, paused, togglePause }
}

export function formatTime(seconds: number | null): string {
  if (seconds === null) return '--:--'
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}
