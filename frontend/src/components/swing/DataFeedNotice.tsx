import { memo } from "react";
import { Card, CardHeader } from "../../design-system";

export type DataFeedNoticeProps = {
  warning?: string | null;
};

/**
 * Data feed / source warning notice for the Swing Decision Dashboard.
 */
export const DataFeedNotice = memo(function DataFeedNotice({ warning }: DataFeedNoticeProps) {
  if (!warning) return null;

  return (
    <Card className="swing-data-feed-notice warning-box" role="status" aria-label="Data feed notice">
      <CardHeader label="Data feed" title="Data feed notice" />
      <p className="ds-muted" style={{ margin: 0 }}>
        {warning}
      </p>
    </Card>
  );
});
