import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { exchangeFyersAuthCode } from "../api";

export default function FyersCallback() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState<"exchanging" | "success" | "error">("exchanging");
  const [message, setMessage] = useState("Completing FYERS authentication...");

  useEffect(() => {
    let mounted = true;
    const authCode = searchParams.get("auth_code");
    const errorDesc = searchParams.get("error_description");

    if (errorDesc) {
      setStatus("error");
      setMessage(`FYERS authentication failed: ${errorDesc}`);
      return;
    }

    if (!authCode) {
      setStatus("error");
      setMessage("No authorization code received from FYERS.");
      return;
    }

    void (async () => {
      try {
        const result = await exchangeFyersAuthCode(authCode);
        if (!mounted) return;
        if (result.status === "ok") {
          setStatus("success");
          setMessage("FYERS authentication successful! Redirecting...");
          setTimeout(() => navigate("/paper?tab=account"), 1500);
        } else {
          setStatus("error");
          setMessage(result.message || "FYERS authentication failed.");
        }
      } catch (e: any) {
        if (!mounted) return;
        setStatus("error");
        setMessage(e?.message || "Failed to complete FYERS authentication.");
      }
    })();

    return () => { mounted = false; };
  }, [searchParams, navigate]);

  return (
    <div className="page-container" style={{ maxWidth: 500, margin: "40px auto", textAlign: "center" }}>
      <section className="panel" style={{ padding: 32 }}>
        {status === "exchanging" && (
          <div>
            <div className="spinner" style={{ margin: "0 auto 16px", width: 32, height: 32 }} />
            <h2>Connecting to FYERS</h2>
            <p className="muted-copy">{message}</p>
          </div>
        )}
        {status === "success" && (
          <div>
            <div style={{ fontSize: 48, marginBottom: 16, color: "var(--signal-bullish)" }}>&#10003;</div>
            <h2>Connected</h2>
            <p className="muted-copy">{message}</p>
          </div>
        )}
        {status === "error" && (
          <div>
            <div style={{ fontSize: 48, marginBottom: 16, color: "var(--signal-bearish)" }}>&#10007;</div>
            <h2>Connection failed</h2>
            <p className="muted-copy">{message}</p>
            <button
              type="button"
              className="button primary-button"
              style={{ marginTop: 16 }}
              onClick={() => navigate("/paper?tab=account")}
            >
              Back to settings
            </button>
          </div>
        )}
      </section>
    </div>
  );
}
