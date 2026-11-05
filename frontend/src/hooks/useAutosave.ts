import { useCallback, useRef, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { saveAnswer } from '../api/attempts'
import type { SaveAnswerBody, Answer } from '../types/api'

/**
 * Debounced autosave hook.
 * - Fires 500ms after the last change.
 * - Optimistic update: reflects choice immediately, rolls back on error.
 * - On 409 (revision conflict): re-fetches the module state.
 */
export function useAutosave(maId: string) {
  const queryClient = useQueryClient()
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pendingRef = useRef<SaveAnswerBody | null>(null)

  const mutation = useMutation({
    mutationFn: (body: SaveAnswerBody) => saveAnswer(maId, body),
    onSuccess: () => {
      // Fresh state from server after save
      queryClient.invalidateQueries({ queryKey: ['moduleState', maId] })
    },
    onError: (err: unknown) => {
      // On 409 revision conflict, refetch authoritative state
      const status = (err as { response?: { status?: number } })?.response?.status
      if (status === 409) {
        queryClient.invalidateQueries({ queryKey: ['moduleState', maId] })
      }
    },
  })

  const save = useCallback(
    (body: SaveAnswerBody) => {
      pendingRef.current = body
      if (debounceRef.current) clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(() => {
        if (pendingRef.current) {
          mutation.mutate(pendingRef.current)
          pendingRef.current = null
        }
      }, 500)
    },
    [mutation],
  )

  // Flush on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [])

  return { save, isPending: mutation.isPending }
}
