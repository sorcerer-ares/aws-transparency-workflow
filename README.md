# 🧟 Zombie Sweeper — Multi-Region AWS Resource & Cost Sweeper

> Built for the **Switch AI Hackathon**.

**Zombie Sweeper** is an interactive, multi-region AWS resource discovery and FinOps sweeper. It scans across all enabled AWS regions in parallel, estimates monthly costs using a zero-latency fallback pricing catalog (or AWS Cost Explorer), classifies resources as Active or Orphaned/Idle, and provides Terraform-style phased destroy plans (`plan-destroy` & `apply-destroy`) with strict dependency ordering and IMDSv2 self-preservation guardrails.

---

## 🌟 Key Features

1. **Multi-Region Parallel Discovery (`inventory.py`)**
   - Automatically queries all enabled regions with `concurrent.futures.ThreadPoolExecutor`.
   - Comprehensive resource coverage: EC2 instances, EBS volumes, EBS snapshots, Elastic IPs, NAT Gateways, ALBs/NLBs, RDS instances, ElastiCache clusters, EKS clusters, ECS clusters, CloudWatch log groups, and S3 buckets.

2. **Instant Cost Engine & Classification (`pricing_catalog.py`, `classifier.py`)**
   - **Zero-Latency Fallback Catalog**: Calculates estimated monthly USD spend for every discovered resource based on instance types, storage sizes, and regional cost multipliers—without incurring Cost Explorer API charges.
   - **Cost Explorer Integration (Opt-in)**: Use `--use-cost-explorer` when actual billing history extrapolation is desired.
   - **Active vs. Orphaned Classification**: Identifies detached EBS volumes, unassociated EIPs, orphaned snapshots (whose source volume is deleted), stopped instances, and idle ECS clusters.

3. **Terraform-Style Phased Destroyer (`planner.py`, `destroyer.py`, `dependency_graph.py`)**
   - **4-Phase Safe Deletion**:
     - *Phase 1*: Compute & Managed Services (EC2, RDS, ElastiCache, EKS, ECS)
     - *Phase 2*: Networking Layer (ALBs, NLBs, NAT Gateways)
     - *Phase 3*: Detached Resources (EBS Volumes, Elastic IPs, Snapshots)
     - *Phase 4*: Observability & Storage (CloudWatch Log retention)
   - **Self-Preservation Guardrails**: Queries IMDSv2 to identify the host EC2 instance and protects it, its root EBS volume, and attached security groups from accidental termination. Whitelist support via `--protect`.
   - **Non-Destructive S3 & RDS Handling**: S3 buckets are list-only in v1; RDS instances with `DeletionProtection` are automatically flagged as protected.
   - **CloudWatch Log Optimization**: Updates retention policy to 7 days instead of deleting logs.

4. **Switch AI Chat Agent Integration (`room.yaml`)**
   - Configured as an interactive FinOps controller room for Slack, Teams, Discord, and Telegram.
   - Safety rule: Requires explicit confirmation phrase `CONFIRM DESTROY` in chat before executing any destructive operations.

---

## 🚀 Installation & Quick Start

### 1. Setup Virtual Environment

```bash
git clone <repo>
cd agy
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. AWS Authentication

Ensure your environment has AWS credentials configured:

```bash
export AWS_DEFAULT_REGION="us-east-1"
# Or use standard AWS credentials/profile
export AWS_PROFILE="my-profile"
```

---

## 💻 CLI Commands

### 🔍 Scan Resources

```bash
# Scan all enabled regions with terminal table output
zombie-sweeper scan --all-regions

# Scan specific regions with JSON output
zombie-sweeper scan --regions us-east-1,ap-south-1 --output json

# Protect specific resource IDs
zombie-sweeper --protect i-0abc123456789def0 --protect vol-0123456789abcdef0 scan --all-regions
```

### 📋 Generate Destroy Plan (`plan-destroy`)

```bash
# Plan destruction for orphaned / idle / stopped resources only
zombie-sweeper plan-destroy --all-regions --orphans-only

# Target specific resource IDs
zombie-sweeper plan-destroy --ids "vol-0abc123,eipalloc-0def456"

# Plan full cleanup across all regions (Dry-Run view)
zombie-sweeper plan-destroy --all-regions --nuke
```

### 💥 Execute Destroy Plan (`apply-destroy`)

```bash
# Execute destroy plan (prompts for typed confirmation "CONFIRM DESTROY")
zombie-sweeper apply-destroy --confirm

# Execute and adjust CloudWatch log retention to 7 days
zombie-sweeper apply-destroy --confirm --set-log-retention
```

### 📋 Reduce CloudWatch Log Retention

```bash
zombie-sweeper set-log-retention --all-regions --days 7
```

---

## 🤖 Switch AI Integration (`room.yaml`)

Mount `room.yaml` into your Switch platform instance:

```yaml
# In chat:
User: "find zombies"
Agent: [Scans AWS and outputs region-by-region cost breakdown table]

User: "plan destroy"
Agent: [Outputs phased destroy plan showing exact $ savings]

User: "CONFIRM DESTROY"
Agent: [Executes Phase 1 -> Phase 2 -> Phase 3 and returns execution summary]
```

---

## 🧪 Testing

```bash
source .venv/bin/activate
pytest tests/ -v
```
