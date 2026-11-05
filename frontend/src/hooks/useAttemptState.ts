import { useQuery } from '@tanstack/react-query'
import { getModuleState } from '../api/attempts'

export function useAttemptState(maId: string | null) {
  return useQuery({
    queryKey: ['moduleState', maId],
    queryFn: () => getModuleState(maId!),
    enabled: !!maId,
    staleTime: 30_000,
    retry: 1,
    refetchOnWindowFocus: false,
  })
}
