import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useTimer, formatTime } from './useTimer'

describe('formatTime', () => {
  it('formats 90 seconds as 01:30', () => {
    expect(formatTime(90)).toBe('01:30')
  })

  it('formats 0 as 00:00', () => {
    expect(formatTime(0)).toBe('00:00')
  })

  it('returns --:-- for null', () => {
    expect(formatTime(null)).toBe('--:--')
  })

  it('formats 3661 seconds as 61:01', () => {
    expect(formatTime(3661)).toBe('61:01')
  })
})

describe('useTimer', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('counts down from deadline', () => {
    const deadline = new Date(Date.now() + 5000).toISOString()
    const onExpire = vi.fn()
    const { result } = renderHook(() => useTimer(deadline, onExpire))

    expect(result.current.secondsLeft).toBeGreaterThan(0)
    expect(result.current.secondsLeft).toBeLessThanOrEqual(5)
  })

  it('calls onExpire when timer hits zero', () => {
    const deadline = new Date(Date.now() + 1000).toISOString()
    const onExpire = vi.fn()
    renderHook(() => useTimer(deadline, onExpire))

    act(() => {
      vi.advanceTimersByTime(2000)
    })

    expect(onExpire).toHaveBeenCalledTimes(1)
  })

  it('does not call onExpire multiple times', () => {
    const deadline = new Date(Date.now() + 500).toISOString()
    const onExpire = vi.fn()
    renderHook(() => useTimer(deadline, onExpire))

    act(() => {
      vi.advanceTimersByTime(5000)
    })

    expect(onExpire).toHaveBeenCalledTimes(1)
  })

  it('returns null when deadlineAt is null', () => {
    const onExpire = vi.fn()
    const { result } = renderHook(() => useTimer(null, onExpire))
    expect(result.current.secondsLeft).toBeNull()
  })
})
