import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  addWatchlistItem,
  connectQuotesWs,
  createWatchlist,
  deleteWatchlist,
  exportWatchlist,
  fetchWatchlists,
  importWatchlist,
  removeWatchlistItem,
  reorderWatchlistItems,
  updateWatchlist,
  type Watchlist,
} from "../../api_retail";

export function WatchlistsPage() {
  const navigate = useNavigate();
  const [lists, setLists] = useState<Watchlist[]>([]);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [newName, setNewName] = useState("");
  const [addSymbol, setAddSymbol] = useState("");
  const [importText, setImportText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState<Record<string, Record<string, unknown>>>({});
  const [dragId, setDragId] = useState<number | null>(null);

  const reload = useCallback(() => {
    void fetchWatchlists()
      .then((data) => {
        setLists(data);
        if (!activeId && data[0]) setActiveId(data[0].id);
      })
      .catch((e: Error) => setError(e.message));
  }, [activeId]);

  useEffect(() => {
    reload();
  }, [reload]);

  const active = useMemo(() => lists.find((l) => l.id === activeId) ?? lists[0] ?? null, [lists, activeId]);

  useEffect(() => {
    if (!active?.items.length) return;
    const symbols = active.items.map((i) => i.symbol);
    const ws = connectQuotesWs((data) => setLive((prev) => ({ ...prev, ...data })));
    ws.subscribe(symbols);
    return () => ws.close();
  }, [active?.id, active?.items]);

  const items = useMemo(() => {
    if (!active) return [];
    const term = search.trim().toUpperCase();
    let rows = active.items;
    if (term) rows = rows.filter((i) => i.symbol.includes(term) || (i.company_name || "").toUpperCase().includes(term));
    return rows.map((item) => {
      const q = live[item.symbol] || {};
      return {
        ...item,
        ltp: (q.ltp as number) ?? item.ltp,
        change: (q.change as number) ?? item.change,
        change_pct: (q.change_pct as number) ?? item.change_pct,
        volume: (q.volume as number) ?? item.volume,
      };
    });
  }, [active, search, live]);

  async function handleCreate() {
    if (!newName.trim()) return;
    const wl = await createWatchlist(newName.trim());
    setNewName("");
    setActiveId(wl.id);
    reload();
  }

  async function handleAdd() {
    if (!active || !addSymbol.trim()) return;
    await addWatchlistItem(active.id, addSymbol.trim().toUpperCase());
    setAddSymbol("");
    reload();
  }

  async function handleImport() {
    const symbols = importText
      .split(/[\s,;\n]+/)
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean);
    if (!symbols.length) return;
    const wl = await importWatchlist(symbols);
    setImportText("");
    setActiveId(wl.id);
    reload();
  }

  async function handleExport() {
    if (!active) return;
    const data = await exportWatchlist(active.id);
    const blob = new Blob([data.symbols.join("\n")], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${data.name}-watchlist.txt`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function onDrop(targetId: number) {
    if (!active || dragId == null || dragId === targetId) return;
    const ids = active.items.map((i) => i.id);
    const from = ids.indexOf(dragId);
    const to = ids.indexOf(targetId);
    if (from < 0 || to < 0) return;
    ids.splice(from, 1);
    ids.splice(to, 0, dragId);
    void reorderWatchlistItems(active.id, ids).then(reload);
    setDragId(null);
  }

  return (
    <div className="dashboard-grid retail-page">
      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="section-label">Watchlists</p>
            <h2>Multi watchlists</h2>
          </div>
          <div className="scanner-actions" style={{ margin: 0 }}>
            <input placeholder="New watchlist" value={newName} onChange={(e) => setNewName(e.target.value)} />
            <button type="button" className="button primary-button" onClick={() => void handleCreate()}>Create</button>
          </div>
        </div>
        <div className="wl-tabs">
          {lists.map((wl) => (
            <button
              key={wl.id}
              type="button"
              className={`wl-tab ${active?.id === wl.id ? "is-active" : ""}`}
              onClick={() => setActiveId(wl.id)}
            >
              {wl.is_pinned ? "📌 " : ""}
              {wl.is_favorite ? "★ " : ""}
              {wl.name}
              <span className="muted-copy"> ({wl.item_count})</span>
            </button>
          ))}
        </div>
        {active ? (
          <div className="wl-toolbar">
            <button type="button" className="button ghost-button" onClick={() => void updateWatchlist(active.id, { is_pinned: !active.is_pinned }).then(reload)}>
              {active.is_pinned ? "Unpin" : "Pin"}
            </button>
            <button type="button" className="button ghost-button" onClick={() => void updateWatchlist(active.id, { is_favorite: !active.is_favorite }).then(reload)}>
              {active.is_favorite ? "Unfavorite" : "Favorite"}
            </button>
            <select
              value={active.sort_by}
              onChange={(e) => void updateWatchlist(active.id, { sort_by: e.target.value }).then(reload)}
            >
              <option value="custom">Custom</option>
              <option value="alphabet">Alphabet</option>
              <option value="change_pct">% Change</option>
              <option value="volume">Volume</option>
              <option value="sector">Sector</option>
            </select>
            <input placeholder="Search inside list" value={search} onChange={(e) => setSearch(e.target.value)} />
            <input placeholder="Add symbol" value={addSymbol} onChange={(e) => setAddSymbol(e.target.value.toUpperCase())} />
            <button type="button" className="button primary-button" onClick={() => void handleAdd()}>Add</button>
            <button type="button" className="button ghost-button" onClick={() => void handleExport()}>Export</button>
            <button type="button" className="button ghost-button" onClick={() => void deleteWatchlist(active.id).then(() => { setActiveId(null); reload(); })}>Delete</button>
          </div>
        ) : null}
        {error ? <div className="warning-box">{error}</div> : null}
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th></th>
                <th>Symbol</th>
                <th>LTP</th>
                <th>Change</th>
                <th>%</th>
                <th>Volume</th>
                <th>Sector</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => {
                const pct = item.change_pct ?? 0;
                return (
                  <tr
                    key={item.id}
                    draggable
                    onDragStart={() => setDragId(item.id)}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={() => onDrop(item.id)}
                    className={pct >= 0 ? "flash-up" : "flash-down"}
                    onClick={() => navigate(`/chart/${item.symbol}`)}
                    style={{ cursor: "pointer" }}
                  >
                    <td className="muted-copy">⋮⋮</td>
                    <td>
                      <strong>{item.symbol}</strong>
                      <div className="muted-copy">{item.company_name}</div>
                    </td>
                    <td>{item.ltp != null ? Number(item.ltp).toFixed(2) : "—"}</td>
                    <td className={pct >= 0 ? "pos" : "neg"}>{item.change != null ? Number(item.change).toFixed(2) : "—"}</td>
                    <td className={pct >= 0 ? "pos" : "neg"}>{item.change_pct != null ? `${Number(item.change_pct).toFixed(2)}%` : "—"}</td>
                    <td>{item.volume != null ? Number(item.volume).toLocaleString("en-IN") : "—"}</td>
                    <td>{item.sector || "—"}</td>
                    <td>
                      <button
                        type="button"
                        className="button ghost-button"
                        onClick={(e) => {
                          e.stopPropagation();
                          if (active) void removeWatchlistItem(active.id, item.id).then(reload);
                        }}
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {!items.length ? <div className="empty-state"><p>No symbols in this watchlist.</p></div> : null}
        </div>
        <div className="scanner-actions" style={{ marginTop: 16 }}>
          <textarea
            placeholder="Import symbols (comma or newline separated)"
            value={importText}
            onChange={(e) => setImportText(e.target.value)}
            rows={2}
          />
          <button type="button" className="button ghost-button" onClick={() => void handleImport()}>Import watchlist</button>
        </div>
      </section>
    </div>
  );
}
