import { useCallback, useEffect, useRef, useState } from "react";
import {
  addFavoriteSymbol,
  recordSymbolSearch,
  removeFavoriteSymbol,
  searchSymbols,
  type SymbolSearchResult,
} from "../../api_retail";

type Props = {
  onSelect: (symbol: string) => void;
  placeholder?: string;
};

export function SymbolSearchBar({ onSelect, placeholder = "Search symbol, name, ISIN…" }: Props) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState<SymbolSearchResult[]>([]);
  const [recent, setRecent] = useState<SymbolSearchResult[]>([]);
  const [trending, setTrending] = useState<SymbolSearchResult[]>([]);
  const [favorites, setFavorites] = useState<SymbolSearchResult[]>([]);
  const [active, setActive] = useState(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  const runSearch = useCallback((query: string) => {
    void searchSymbols(query, 15)
      .then((r) => {
        setResults(r.results);
        setRecent(r.recent);
        setTrending(r.trending);
        setFavorites(r.favorites);
        setActive(0);
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => runSearch(q), 250);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [q, runSearch]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  const list: SymbolSearchResult[] = q.trim()
    ? results
    : [...favorites, ...recent, ...trending].filter(
        (item, i, arr) => arr.findIndex((x) => x.symbol === item.symbol) === i,
      );

  function pick(item: SymbolSearchResult) {
    void recordSymbolSearch(item.symbol);
    onSelect(item.symbol);
    setQ("");
    setOpen(false);
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (!open) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, list.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter" && list[active]) {
      e.preventDefault();
      pick(list[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  async function toggleFav(e: React.MouseEvent, item: SymbolSearchResult) {
    e.stopPropagation();
    if (item.is_favorite) await removeFavoriteSymbol(item.symbol);
    else await addFavoriteSymbol(item.symbol);
    runSearch(q);
  }

  return (
    <div className="symbol-search" ref={wrapRef}>
      <input
        type="search"
        className="symbol-search-input"
        placeholder={placeholder}
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
        }}
        onFocus={() => {
          setOpen(true);
          runSearch(q);
        }}
        onKeyDown={onKeyDown}
        aria-autocomplete="list"
        aria-expanded={open}
        data-testid="symbol-search"
      />
      {open ? (
        <div className="symbol-search-dropdown" role="listbox">
          {!q.trim() ? (
            <>
              {favorites.length ? <div className="search-section-label">Favorites</div> : null}
              {recent.length ? <div className="search-section-label">Recent</div> : null}
              {trending.length && !recent.length ? <div className="search-section-label">Trending</div> : null}
            </>
          ) : (
            <div className="search-section-label">{results.length} results</div>
          )}
          {list.map((item, i) => (
            <button
              key={item.symbol}
              type="button"
              role="option"
              aria-selected={i === active}
              className={`symbol-search-row ${i === active ? "is-active" : ""}`}
              onMouseEnter={() => setActive(i)}
              onClick={() => pick(item)}
            >
              <div>
                <strong>{item.symbol}</strong>
                <span className="muted-copy"> {item.company_name}</span>
              </div>
              <div className="symbol-search-meta">
                <span className="helper-chip">{item.instrument_type || "EQ"}</span>
                {item.sector ? <span className="muted-copy">{item.sector}</span> : null}
                <span
                  role="button"
                  tabIndex={0}
                  className="fav-toggle"
                  onClick={(e) => void toggleFav(e, item)}
                  onKeyDown={(e) => e.key === "Enter" && void toggleFav(e as unknown as React.MouseEvent, item)}
                >
                  {item.is_favorite ? "★" : "☆"}
                </span>
              </div>
            </button>
          ))}
          {!list.length ? <div className="muted-copy" style={{ padding: 12 }}>No symbols found</div> : null}
        </div>
      ) : null}
    </div>
  );
}
