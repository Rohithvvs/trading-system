import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { Card, Tabs, TabPanel } from "../../design-system";
import type { TabItem } from "../../design-system";
import { UsersAdminTab } from "./UsersAdminTab";
import { FeaturesAdminTab } from "./FeaturesAdminTab";

const TAB_ITEMS: TabItem[] = [
  { id: "users", label: "Users" },
  { id: "features", label: "Features" },
];

function normalizeTab(raw: string | null): "users" | "features" {
  if (raw === "features") return "features";
  return "users";
}

export function AdminPanelPage() {
  const [params, setParams] = useSearchParams();
  const tab = useMemo(() => normalizeTab(params.get("tab")), [params]);

  function setTab(id: string) {
    const next = normalizeTab(id);
    const sp = new URLSearchParams(params);
    sp.set("tab", next);
    setParams(sp, { replace: true });
  }

  return (
    <div className="page-container" data-testid="admin-panel-page">
      <div style={{ marginBottom: 20 }}>
        <p className="ds-label">Administration</p>
        <h1 className="ds-heading">Admin</h1>
        <p className="ds-muted" style={{ marginTop: 6, maxWidth: 560 }}>
          Manage users and feature visibility. Changes apply through live admin APIs.
        </p>
      </div>

      <Card>
        <Tabs
          items={TAB_ITEMS}
          value={tab}
          onChange={setTab}
          ariaLabel="Admin sections"
          variant="underline"
        />
        <div style={{ marginTop: 20 }}>
          <TabPanel id="users" activeId={tab}>
            <UsersAdminTab />
          </TabPanel>
          <TabPanel id="features" activeId={tab}>
            <FeaturesAdminTab />
          </TabPanel>
        </div>
      </Card>
    </div>
  );
}
