import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

const STORAGE_KEY = "developer_mode";

type DeveloperModeContextValue = {
  /** When true, engineering/ops pages are visible */
  developerMode: boolean;
  setDeveloperMode: (on: boolean) => void;
  toggleDeveloperMode: () => void;
};

const DeveloperModeContext = createContext<DeveloperModeContextValue | null>(null);

function readFlag(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

export function DeveloperModeProvider({ children }: { children: ReactNode }) {
  const [developerMode, setState] = useState(false);

  useEffect(() => {
    setState(readFlag());
  }, []);

  const setDeveloperMode = useCallback((on: boolean) => {
    setState(on);
    try {
      localStorage.setItem(STORAGE_KEY, on ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, []);

  const toggleDeveloperMode = useCallback(() => {
    setDeveloperMode(!developerMode);
  }, [developerMode, setDeveloperMode]);

  const value = useMemo(
    () => ({ developerMode, setDeveloperMode, toggleDeveloperMode }),
    [developerMode, setDeveloperMode, toggleDeveloperMode],
  );

  return (
    <DeveloperModeContext.Provider value={value}>{children}</DeveloperModeContext.Provider>
  );
}

export function useDeveloperMode(): DeveloperModeContextValue {
  const ctx = useContext(DeveloperModeContext);
  if (!ctx) {
    return {
      developerMode: false,
      setDeveloperMode: () => undefined,
      toggleDeveloperMode: () => undefined,
    };
  }
  return ctx;
}
