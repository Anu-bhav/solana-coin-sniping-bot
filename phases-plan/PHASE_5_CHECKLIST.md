# Phase 5 Checklist: Controlled Mainnet Transition, Monitoring & Iteration

**Goal:** Safely transition to Mainnet, evaluate real-world performance, make informed decisions about upgrades, and establish ongoing operations.

**Pre-Flight Checklist:**

*   [ ] Confirm all Phase 4 Devnet E2E tests passed successfully.
*   [ ] Confirm no major code changes since successful Devnet tests.
*   [ ] Generate **NEW dedicated Mainnet wallet**.
*   [ ] Secure Mainnet private key in `.env.prod`.
*   [ ] Fund Mainnet wallet with **MINIMAL** SOL (Gas + 5-10 micro-buys ONLY).
*   [ ] Verify `config.yml` is configured for Mainnet (`rpc.network`, paths, minimal `buy_amount_sol`, `general.dry_run` initially true). **Double-check Mainnet Program IDs.**
*   [ ] Verify `.env.prod` contains correct Mainnet RPC URLs / API Keys (paid or free tier as decided).
*   [ ] Confirm production SQLite DB backup strategy is in place.
*   [ ] Confirm production server is ready (secure, updated).
*   [ ] Confirm process manager (`systemd`/`supervisor`) is configured for production run (`APP_ENV=production`).
*   [ ] Confirm log monitoring and critical alerting system are active and tested.
*   [ ] Confirm manual kill switch procedure is known and accessible.

**Initial Mainnet Deployment (`dry_run=True`):**

*   [ ] Deploy tested code to production server.
*   [ ] Start bot service with `APP_ENV=production`, `dry_run=True`.
*   [ ] Monitor logs for successful Mainnet WSS/RPC connection.
*   [ ] Observe detection and filter processing against live Mainnet data.
*   [ ] Verify simulated execution logs appear correctly.
*   [ ] Monitor server resources (CPU, RAM).
*   [ ] Check for Mainnet-specific errors or rate limiting.
*   [ ] Run in dry run mode for at least 24-48 hours successfully.

**First Live Mainnet Trades (`dry_run=False` - Micro-Capital):**

*   [ ] Verify minimal `buy_amount_sol` in config.
*   [ ] Stop dry run process. Set `dry_run=False` in `config.yml`.
*   [ ] Restart bot service for live trading.
*   [ ] **Monitor 24/7:**
    *   [ ] Watch Logs continuously.
    *   [ ] Watch Bot Wallet on Solscan Mainnet.
    *   [ ] Watch relevant token charts/trades on DEX explorers.
    *   [ ] Check SQLite DB (`positions`, `trades`) periodically.
    *   [ ] Respond immediately to Alerts.
*   [ ] Verify first full trade lifecycle (Detect -> Filter -> Buy -> Monitor -> Sell) completes successfully on Mainnet. Check TXs on Solscan. Check DB state.

**Performance Evaluation & Bottleneck Analysis:**

*   [ ] Allow bot to run with micro-capital for sufficient data collection period (days/weeks).
*   [ ] Collect data points (Filter Rate/Accuracy, Execution Rate/Latency, Slippage, PnL, Error Rates).
*   [ ] Analyze data to identify primary bottlenecks (Detection, Filtering Data, Filtering Logic, Execution Speed/Reliability, Rate Limits).

**Decision Point & Iteration:**

*   [ ] Review performance data objectively.
*   [ ] **Decision Made:**
    *   [ ] Option 1: Tune `config.yml` parameters. Document changes. Restart & Re-evaluate.
    *   [ ] Option 2: Implement targeted Paid Upgrade (Document which one - e.g., Paid RPC). Deploy upgrade, re-test, re-evaluate.
    *   [ ] Option 3: Halt live trading. Document reasons. Plan next steps (refactor/pivot/abandon).
*   [ ] If continuing, establish cycle for ongoing monitoring, tuning, and adaptation.
*   [ ] Only consider gradual scaling if *consistent positive PnL* is proven over time (highly cautious).

**Ongoing Maintenance:**

*   [ ] Establish routine for checking logs, performance, DB backups.
*   [ ] Subscribe to updates for Solana, DEXs, used APIs, libraries. Plan for adaptation.

**Completion:**

*   [ ] Bot is either running stably on Mainnet (potentially with upgrades), undergoing tuning, or operations have been consciously halted based on data.
*   [ ] Monitoring and maintenance procedures are in place.