# 🧟 Zombie Sweeper — Switch Integration & Project Runbook

> **Switch AI Hackathon Submission**  
> **Project:** Zombie Sweeper (Multi-Region AWS Resource & FinOps Controller)  
> **Agent:** `Zombie Sweeper` (FinOps Controller)  
> **Interface:** Slack (`#finops-sweeper`) via Switch Room Connector  

---

## 1. Overview & Architecture

**Zombie Sweeper** uses **Switch** as its agentic orchestration and Human-in-the-Loop (HITL) communication platform. Instead of requiring DevOps and FinOps engineers to manually log in to the AWS Management Console or run repetitive terminal scripts, Switch connects an intelligent AI agent directly into team chat (Slack).

### End-to-End Architecture Flow

```
┌─────────────────┐       Slack Messages       ┌────────────────────────┐
│  Slack Channel  │ ◄────────────────────────► │ Switch Gateway (Nginx) │
│ #finops-sweeper │      (@Zombie Sweeper scan,       │    Port 3000 / SSE     │
└─────────────────┘       plan, destroy)       └───────────┬────────────┘
                                                           │
                                                           ▼
                                               ┌────────────────────────┐
                                               │   Switch Core Engine   │
                                               │      (Port 8000)       │
                                               └───────────┬────────────┘
                                                           │
                                                           ▼
                                               ┌────────────────────────┐
                                               │     Switch Console     │
                                               │   & Shared SDK Host    │
                                               │  (Agent: Zombie Sweeper / AGY)│
                                               └───────────┬────────────┘
                                                           │
                                                           ▼
                                               ┌────────────────────────┐
                                               │ zombie-sweeper CLI     │
                                               │   & Boto3 Multi-Region │
                                               │  (All AWS Regions)     │
                                               └────────────────────────┘
```

---

## 2. Which Agents Were Connected

### Agent Profile
- **Agent Name:** `Zombie Sweeper`
- **Agent Provider / Runtime:** Antigravity CLI (`antigravity` via Switch Shared SDK Host)
- **Role:** `finops-controller` (defined in `room.yaml`)
- **Assigned Tools / Capabilities:**
  - `zombie-sweeper scan`: Multi-region parallel resource scanner querying EC2, EBS, RDS, ElastiCache, EKS, ECS, ALBs, NAT Gateways, EIPs, S3, and CloudWatch.
  - `zombie-sweeper plan-destroy`: 4-phase dependency-aware destruction planner.
  - `zombie-sweeper apply-destroy`: Safe execution engine with IMDSv2 self-preservation protection.
  - `zombie-sweeper set-log-retention`: Automated CloudWatch cost reducer (7-day retention).

### Permissions & Human-in-the-Loop Safety Boundaries
The agent runs in a sandboxed, permission-controlled environment inside Switch:
1. **Autonomous Read & Discovery:**
   - Routine scanning (`zombie-sweeper scan`, `plan-destroy`, `ls`, `which`) runs autonomously without prompting the user for approval.
2. **Strict Human Confirmation Gate (Zero Unintended Deletions):**
   - The agent instructions strictly forbid running any destructive deletion command (`apply-destroy`) unless the user explicitly types the exact phrase:
     ```text
     CONFIRM DESTROY
     ```
   - Vague confirmations like *"yes"*, *"do it"*, or *"proceed"* are rejected by the agent with a warning prompt requesting the exact phrase.
3. **Self-Preservation & Protected Resources:**
   - IMDSv2 queries automatically protect the host machine, root EBS volumes, and security groups.
   - Protected resources whitelisted via `--protect` or flagged with `DeletionProtection` are excluded from destruction.

---

## 3. How the Channel is Set Up

### 1. Platform & Channel Details
- **Chat Platform:** Slack (integrated through Switch room connector)
- **Room Name:** `Slack: finops-sweeper`
- **Channel Target:** `#finops-sweeper`

### 2. Room Configuration (`room.yaml`)
The room is mounted into Switch using the declarative template:

```yaml
version: "v1"
kind: room-template
metadata:
  name: "zombie-sweeper-finops"
  description: "FinOps controller — scans AWS for zombie resources and generates safe destroy plans."

spec:
  platform: slack
  channel: "#finops-sweeper"

  agents:
    - id: zombie-sweeper-agent
      role: finops-controller
      addressing_policy: anyone

  packages:
    - id: aws-cli-tools

  rules:
    - >
      You are Zombie Sweeper, an AWS FinOps controller agent.
      Always be helpful, precise, and cautious with destructive operations.
    - >
      When a user asks to scan AWS (e.g. "scan", "find zombies", "scan us-east-1"):
        1. Run `zombie-sweeper scan --all-regions --output json` (or `--regions <region>`).
        2. Present a region-by-region cost breakdown table.
        3. Highlight orphaned/idle resources with 🔴 or 🟠.
        4. Display estimated total monthly spend.
    - >
      When a user says "plan destroy" or "what can we kill":
        1. Run `zombie-sweeper plan-destroy --all-regions --orphans-only --output json`.
        2. Present the 4-phase execution plan and estimated savings.
        3. Display protected resources (🛡️).
        4. Remind user: "Type CONFIRM DESTROY to execute this plan."
    - >
      CRITICAL SAFETY RULE: NEVER execute apply-destroy unless the user types
      the EXACT phrase: CONFIRM DESTROY.
```

---

## 4. How to Run It (Step-by-Step Runbook)

### Prerequisites
- **OS:** Linux or WSL2 (Ubuntu 22.04 / 24.04 LTS)
- **Python:** 3.11+
- **Docker & Docker Compose**
- **GNOME Keyring / libsecret** (`gnome-keyring`, `secret-tool`)
- **AWS Credentials:** Configured with read/write permissions specified in `iam-policy.json`.

---

### Step 1: Install Zombie Sweeper CLI

```bash
cd ~/project/agy

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies and CLI in editable mode
pip install -e .

# Verify installation
zombie-sweeper --help
```

---

### Step 2: Start the Switch Backend Stack

Start the core Switch services (PostgreSQL, Switch Core, Mattermost/Slack connector, Gateway Nginx):

```bash
cd ~/switch-local/switch
just standalone-up
```

*Note: Ensure the Switch Gateway Nginx configuration (`deploy/shared_resources/gateway-nginx.conf`) includes proxy rules for `/agents` and `/agent-sessions` so WebSockets and SSE streams route cleanly to Switch Core on port 8000.*

Verify the gateway is running:
```bash
curl -I http://127.0.0.1:3000
```

---

### Step 3: Launch Switch Console

Launch the desktop console using the helper script that securely manages GNOME Keyring in headless/WSL2 environments:

```bash
~/start-switch.sh
```

- If prompted in the terminal, enter your keyring password to unlock credentials.
- The Switch Console Electron UI will launch and connect to the local gateway (`http://127.0.0.1:3000`).

---

### Step 4: Verify the Agent Connection

1. In **Switch Console**, navigate to **Agents**.
2. Select or register the agent **`Zombie Sweeper`**.
3. Verify that the agent instructions match `room.yaml` and that permissions allow `mcp__switch` and CLI tool execution.
4. Ensure the session connects to the room **`Slack: finops-sweeper`**.

---

### Step 5: Interact from Slack

Go to your Slack workspace in the `#finops-sweeper` channel and interact with the bot:

#### 1. Scan for Zombie Resources & Cost
```text
@Zombie Sweeper scan
```
*or scan a specific region:*
```text
@Zombie Sweeper scan us-east-1
```
> **Agent Action:** Runs `zombie-sweeper scan`, collects resource inventories across regions in parallel, and posts a formatted markdown table showing active vs. orphaned resources with estimated monthly spend.

---

#### 2. Generate a Phased Destroy Plan
```text
@Zombie Sweeper plan destroy
```
> **Agent Action:** Identifies detached EBS volumes, unassociated EIPs, orphaned snapshots, and stopped instances. Outputs a dependency-ordered 4-phase plan with projected cost savings.

---

#### 3. Execute Deletion (Safeguarded)
```text
@Zombie Sweeper CONFIRM DESTROY
```
> **Agent Action:** Verifies the safety phrase, triggers `zombie-sweeper apply-destroy --confirm`, preserves protected resources via IMDSv2, and streams progress updates back to Slack.

---

#### 4. Optimize CloudWatch Log Retention
```text
@Zombie Sweeper set log retention
```
> **Agent Action:** Updates all CloudWatch log groups with indefinite retention to a cost-effective 7-day retention period.

---

## 5. Security & Verification

- **Read IAM Policy:** See [`iam-policy.json`](./iam-policy.json) for minimal required AWS permissions.
- **Unit & Integration Tests:**
  ```bash
  source .venv/bin/activate
  pytest tests/ -v
  ```
