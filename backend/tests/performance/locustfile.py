from locust import HttpUser, task, between

class TradingBackendUser(HttpUser):
    wait_time = between(1, 5)

    @task(3)
    def engine_heartbeat(self):
        """Simulate cron jobs / keepalives hitting the heartbeat endpoint"""
        self.client.post("/engine/heartbeat")

    @task(1)
    def fetch_dashboard_rankings(self):
        """Simulate users loading the dashboard rankings"""
        self.client.post(
            "/analysis/screener/full",
            json={
                "universe": "NIFTY50",
                "mode": "swing",
                "timeframe_config": {
                    "intraday": "5m",
                    "swing": "1d",
                    "lookback_window": 180
                },
                "top_n": 5,
                "custom_symbols": []
            }
        )

    @task(2)
    def fetch_market_status(self):
        self.client.get("/engine/status")
