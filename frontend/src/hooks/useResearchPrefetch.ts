import { useCallback } from "react";
import { prefetchResearch } from "../utils/researchPrefetcher";

/**
 * Hook that returns event handlers for prefetching research data
 * on hover, focus, and context menu open.
 */
export function useResearchPrefetch() {
  const handlePrefetch = useCallback((symbol: string) => {
    prefetchResearch(symbol);
  }, []);

  const hoverHandlers = useCallback(
    (symbol: string) => ({
      onMouseEnter: () => handlePrefetch(symbol),
      onFocus: () => handlePrefetch(symbol),
      onTouchStart: () => handlePrefetch(symbol),
    }),
    [handlePrefetch],
  );

  return { handlePrefetch, hoverHandlers };
}
