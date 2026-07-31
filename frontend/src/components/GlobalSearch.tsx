import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

export function GlobalSearch() {
  const [query, setQuery] = useState("");
  const navigate = useNavigate();

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = query.trim().toUpperCase();
    if (trimmed) {
      navigate(`/research/workstation?symbol=${encodeURIComponent(trimmed)}`);
      setQuery("");
    }
  }

  return (
    <form onSubmit={handleSubmit} className="global-search-form" style={{ position: "relative", width: "220px" }}>
      <input
        type="text"
        placeholder="Search symbol (e.g. INFY)..."
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        className="ds-input"
        style={{
          width: "100%",
          padding: "6px 12px 6px 32px",
          fontSize: "0.85rem",
          borderRadius: "var(--radius-full, 999px)",
          background: "var(--surface-2, #1a222d)",
          border: "1px solid var(--border, #2a3444)",
          color: "var(--text, #f0f4f8)",
        }}
        data-testid="global-search-input"
      />
      <svg
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        style={{
          position: "absolute",
          left: "10px",
          top: "50%",
          transform: "translateY(-50%)",
          color: "var(--text-muted)",
          pointerEvents: "none",
        }}
        aria-hidden
      >
        <circle cx="11" cy="11" r="8" />
        <line x1="21" y1="21" x2="16.65" y2="16.65" />
      </svg>
    </form>
  );
}
