import {
  createContext,
  useCallback,
  useContext,
  useLayoutEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type DensityMode = "comfortable" | "compact";

const STORAGE_KEY = "ui_density";

type DensityContextValue = {
  density: DensityMode;
  setDensity: (mode: DensityMode) => void;
  toggleDensity: () => void;
};

const DensityContext = createContext<DensityContextValue | null>(null);

function readDensity(): DensityMode {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === "compact" || v === "comfortable") return v;
  } catch {
    /* ignore */
  }
  return "comfortable";
}

export function DensityProvider({ children }: { children: ReactNode }) {
  const [density, setDensityState] = useState<DensityMode>(() =>
    typeof window === "undefined" ? "comfortable" : readDensity(),
  );

  useLayoutEffect(() => {
    document.documentElement.dataset.density = density;
    try {
      localStorage.setItem(STORAGE_KEY, density);
    } catch {
      /* ignore */
    }
  }, [density]);

  const setDensity = useCallback((mode: DensityMode) => {
    setDensityState(mode);
  }, []);

  const toggleDensity = useCallback(() => {
    setDensityState((d) => (d === "comfortable" ? "compact" : "comfortable"));
  }, []);

  const value = useMemo(
    () => ({ density, setDensity, toggleDensity }),
    [density, setDensity, toggleDensity],
  );

  return <DensityContext.Provider value={value}>{children}</DensityContext.Provider>;
}

export function useDensity(): DensityContextValue {
  const ctx = useContext(DensityContext);
  if (!ctx) {
    return {
      density: "comfortable",
      setDensity: () => undefined,
      toggleDensity: () => undefined,
    };
  }
  return ctx;
}
