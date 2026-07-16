import { memo } from "react";
import { useNavigate } from "react-router-dom";
import { Button, Card, CardHeader } from "../../design-system";

export type QuickScannerActionsProps = {
  hasResults?: boolean;
  isLoading?: boolean;
  favoritesCount?: number;
  resultsCount?: number;
  onRunScanner?: () => void;
};

/**
 * Quick actions after configuring / running a scan from Markets.
 */
export const QuickScannerActions = memo(function QuickScannerActions({
  hasResults = false,
  isLoading = false,
  favoritesCount = 0,
  resultsCount = 0,
  onRunScanner,
}: QuickScannerActionsProps) {
  const navigate = useNavigate();

  return (
    <Card className="swing-quick-actions" aria-label="Quick scanner actions">
      <CardHeader
        label="Quick actions"
        title="Continue to scanner results"
        description="Favorites and full scan tables live on the Scanner page."
      />
      <div className="markets-quick-trade swing-quick-actions__row">
        <Button
          variant="trade"
          onClick={() => navigate("/scanner")}
          disabled={isLoading}
        >
          {hasResults
            ? `View results${favoritesCount ? ` · ${favoritesCount} favorites` : resultsCount ? ` · ${resultsCount}` : ""}`
            : "Open Scanner"}
        </Button>
        {onRunScanner ? (
          <Button variant="secondary" onClick={onRunScanner} disabled={isLoading} loading={isLoading}>
            {isLoading ? "Scanning…" : "Run again"}
          </Button>
        ) : null}
        <Button variant="ghost" onClick={() => navigate("/watchlist")}>
          Watchlist
        </Button>
      </div>
    </Card>
  );
});
