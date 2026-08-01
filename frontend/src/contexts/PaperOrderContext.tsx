import { createContext, useContext, useState, useCallback, useRef, type ReactNode } from "react";
import type { PaperOrderTicketState, RecommendationPrefillRequest } from "../types";

export type DrawerState = {
  open: boolean;
  symbol?: string;
  side?: "BUY" | "SELL";
  prefill?: RecommendationPrefillRequest | null;
  orderId?: number | null;
};

type PaperOrderContextValue = {
  drawerState: DrawerState;
  openOrderDrawer: (symbol?: string, side?: "BUY" | "SELL", prefill?: RecommendationPrefillRequest | null, orderId?: number | null) => void;
  closeOrderDrawer: () => void;
  ticketRef: React.MutableRefObject<PaperOrderTicketState | null>;
};

const PaperOrderContext = createContext<PaperOrderContextValue | null>(null);

export function PaperOrderProvider({ children }: { children: ReactNode }) {
  const [drawerState, setDrawerState] = useState<DrawerState>({ open: false });
  const ticketRef = useRef<PaperOrderTicketState | null>(null);

  const openOrderDrawer = useCallback(
    (symbol?: string, side?: "BUY" | "SELL", prefill?: RecommendationPrefillRequest | null, orderId?: number | null) => {
      ticketRef.current = null;
      setDrawerState({ open: true, symbol, side, prefill, orderId });
    },
    [],
  );

  const closeOrderDrawer = useCallback(() => {
    setDrawerState({ open: false, symbol: undefined, side: undefined, prefill: undefined, orderId: undefined });
  }, []);

  return (
    <PaperOrderContext.Provider value={{ drawerState, openOrderDrawer, closeOrderDrawer, ticketRef }}>
      {children}
    </PaperOrderContext.Provider>
  );
}

export function usePaperOrder(): PaperOrderContextValue {
  const ctx = useContext(PaperOrderContext);
  if (!ctx) {
    return {
      drawerState: { open: false },
      openOrderDrawer: () => undefined,
      closeOrderDrawer: () => undefined,
      ticketRef: { current: null },
    };
  }
  return ctx;
}
