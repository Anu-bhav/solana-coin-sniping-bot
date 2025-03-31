# Phase 5: Controlled Mainnet Transition, Monitoring & Iteration

**Goal:** Carefully transition the validated bot to the Solana Mainnet environment, starting with extremely limited capital and intensive monitoring. Evaluate real-world performance, identify bottlenecks specific to Mainnet, make data-driven decisions about necessary upgrades (like paid RPC), and establish a cycle of ongoing maintenance and adaptation.

**Duration Estimate:** Ongoing / Indefinite

**Key Activities & Actions:**

1.  **Rigorous Pre-Flight Checklist Completion:**
    *   **Confirm Devnet Success:** Verify all Phase 4 Devnet E2E tests (Dry Run and Live SOL) passed successfully for the chosen primary execution provider. All known critical bugs fixed.
    *   **Code Freeze (Temporary):** Avoid significant code changes immediately before Mainnet launch. Ensure the deployed version matches the thoroughly tested Devnet version.
    *   **Mainnet Configuration (`.env.prod`, `config.yml`):**
        *   Generate a **NEW, dedicated Mainnet wallet**. Secure the private key in `.env.prod`.
        *   Fund the Mainnet wallet with **strictly minimal capital**: Enough SOL for gas for ~20-50 TX attempts + the SOL equivalent for **only 5-10 minimum-sized buys** (e.g., if `buy_amount_sol: 0.01`, fund with 0.05-0.1 SOL + gas buffer). **DO NOT OVERFUND.**
        *   Update `config.yml` for production: Set `rpc.network: "mainnet-beta"`. Ensure `general.dry_run` is set correctly for initial Mainnet tests. Verify all thresholds, amounts (`buy_amount_sol` set to minimum), file paths (`database.mainnet_db_config.db_file`, `logging.log_file_path`) are appropriate for Mainnet. **Double-check Program IDs** for Raydium/PumpSwap on Mainnet.
        *   If using paid RPC, update `.env.prod` with Mainnet RPC URLs and API keys. If using Sniperoo, ensure the Mainnet API key is in `.env.prod`.
    *   **Database Backup:** Ensure a reliable backup mechanism is in place for the production SQLite database file.
    *   **Deployment Environment Ready:** Secure VPS configured, necessary software installed, firewall rules set. Process manager (`systemd`/`supervisor`) configured to run the bot script using `APP_ENV=production`.
    *   **Monitoring & Alerting Setup:** Configure log monitoring (e.g., `tail -f`, basic log analysis scripts, or a proper logging stack) and critical alerts (e.g., Telegram bot notifications for errors, successful buys/sells, low balance).
    *   **Manual Kill Switch Ready:** Have immediate SSH access to the server and know the command to stop the bot process instantly (`systemctl stop <service>`, `supervisorctl stop <process>`, or `pkill`).

2.  **Initial Mainnet Deployment (`dry_run=True`):**
    *   Deploy the latest tested code to the production server.
    *   Start the bot using the process manager with `APP_ENV=production` and `dry_run: true` in `config.yml`.
    *   **Intensive Monitoring (Logs & System):**
        *   Watch logs for successful connection to Mainnet WSS/RPC.
        *   Observe detection events from *real* Mainnet activity.
        *   Verify filter logic executes correctly against Mainnet tokens. Check filter pass/fail reasons.
        *   Check DB updates (detections table).
        *   Verify *simulated* buy/sell logs trigger appropriately.
        *   Monitor server resource usage (CPU, RAM, network).
        *   Check for any new errors specific to Mainnet (e.g., different API behaviors, unexpected log formats, rate limiting hits *even on free tiers* due to higher traffic).
    *   **Duration:** Run in `dry_run` mode on Mainnet for at least 24-48 hours to gain confidence in stability and basic processing against live data.

3.  **First Live Mainnet Trades (`dry_run=False` - Micro-Capital ONLY):**
    *   **Final Check:** Review wallet balance, config (`buy_amount_sol` is minimal, `dry_run: false`).
    *   **Start Live Trading:** Stop the dry run process, set `dry_run: false` in `config.yml`, restart the bot via the process manager.
    *   **EXTREMELY Intensive Monitoring (24/7 initially):**
        *   **Logs:** Watch every line for detections, filter decisions, execution attempts, confirmations, monitoring actions, errors.
        *   **Solscan Mainnet:** Have the bot's wallet address open. Immediately check every outgoing transaction initiated by the bot. Verify target contract, amount, fees, confirmation status, success/failure. Check incoming tokens from buys and outgoing tokens from sells.
        *   **DEX Frontend/Explorer:** Monitor the price chart and trades for the tokens the bot interacts with on DexScreener/Birdeye.
        *   **SQLite DB:** Periodically check the `positions` and `trades` tables directly to verify state matches reality.
        *   **Alerts:** Respond immediately to any critical error alerts.
        *   **Manual Override:** Be ready to use the kill switch instantly if the bot behaves erratically (e.g., rapid unexpected trades, massive transaction failures, significant unexpected losses).
    *   **Goal:** Observe the *entire lifecycle* of a few trades (Detection -> Filter -> Buy -> Monitor -> Sell (TP/SL/Time)) successfully execute on Mainnet with minimal capital. Identify immediate failures or critical bugs.

4.  **Performance Evaluation & Bottleneck Analysis (Data Collection):**
    *   **Run Duration:** Let the bot run with micro-capital for a significant period (e.g., 1-2 weeks) to gather enough data points, *accepting that it will likely lose money initially*.
    *   **Data Points to Collect (from Logs & DB):**
        *   Detection Rate & Latency (if measurable).
        *   Filter Pass Rate (% of detected tokens passing filters).
        *   Filter Accuracy (Manual review: How many passed tokens were scams? How many good tokens were filtered out?).
        *   Buy Execution Success Rate & Latency (Time from filter pass to TX confirmation). Slippage incurred.
        *   Sell Execution Success Rate & Latency (TP & SL).
        *   Average Holding Time.
        *   Win Rate (% of closed trades with positive PnL).
        *   Profit Factor (Gross Profit / Gross Loss).
        *   Net PnL (after gas fees).
        *   Frequency and type of errors (RPC errors, API rate limits, TX failures).
    *   **Identify Bottlenecks:** Based on the data, determine the weakest links:
        *   *Detection too slow/unreliable?* (WSS issues on free tier?)
        *   *Filtering ineffective?* (Letting scams through? Too strict?) -> Needs better data (paid APIs)? Better logic?
        *   *Buy/Sell TXs failing/slow?* -> RPC node performance? Priority fees too low? Need Jito? Execution logic flawed?
        *   *Rate limits constantly hit?* -> Need paid API tiers? Need to optimize API usage?

5.  **Decision Point: Tune, Upgrade, or Halt:**
    *   **Analyze Data Objectively:** Is the bot functional? Is the loss rate acceptable for the learning phase? What is the primary cause of failures or losses?
    *   **Option 1: Tune (If core logic is sound but parameters off):**
        *   Adjust `config.yml`: Modify filter thresholds, TP/SL percentages, timing intervals, priority fees. Restart and continue monitoring.
    *   **Option 2: Strategic Paid Upgrade (If infrastructure is the bottleneck):**
        *   **Most Likely First Upgrade: Paid RPC Node.** Switch to Helius/QuickNode paid plan. Update `.env.prod` with new URLs/keys. Re-test performance. This should improve detection stability, filtering speed (for RPC checks), and execution reliability.
        *   **Subsequent Upgrades (Based on data):** If filtering is still weak -> Paid Helius API tier for better holder data OR Paid security API (GoPlus). If execution speed is still lacking -> Implement/use Jito Bundles via paid RPC. If pattern analysis needed -> Paid DexScreener/Birdeye for WebSockets. Introduce upgrades *one at a time* and evaluate impact.
    *   **Option 3: Halt/Pivot:** If the bot is fundamentally flawed, consistently losing money rapidly even after tuning, or hitting insurmountable free-tier limitations, halt live trading. Re-evaluate the strategy, consider a major code refactor, or abandon the sniping approach.

6.  **Ongoing Maintenance & Iteration Cycle:**
    *   **Continuous Monitoring:** Regular checks of logs, performance, PnL, wallet balance.
    *   **Adaptation:** Update code for DEX changes, Solana updates, API modifications. Stay informed about new scam tactics and adapt filters.
    *   **Performance Tuning:** Regularly analyze trade data to refine config parameters.
    *   **Database Management:** Implement backups, potentially prune old detection logs from the DB.
    *   **Security Review:** Periodically review code and server security.
    *   **Gradual Scaling (Use Extreme Caution):** Only if the bot demonstrates *consistent, verifiable positive PnL* after upgrades and tuning over an extended period, *consider* very slowly increasing the `buy_amount_sol`. Any scaling increases risk significantly.

**Key Considerations for Mainnet:**

*   **Increased Competition:** Far more sophisticated bots operate on Mainnet.
*   **Higher Fees / Volatility:** Gas fees and priority fee requirements fluctuate more wildly. Price action is faster and more volatile.
*   **Real Financial Loss:** Mistakes directly cost real money.
*   **Monitoring is Non-Negotiable:** Cannot "set and forget." Requires active oversight, especially early on.

**Expected Deliverables:**

*   Documented Pre-Flight Checklist results.
*   Deployment scripts/process documentation.
*   Monitoring and alerting setup.
*   Logs and performance data from initial Mainnet `dry_run` and micro-capital phases.
*   Data-driven decision on tuning, upgrades, or halting.
*   Established ongoing maintenance procedures.