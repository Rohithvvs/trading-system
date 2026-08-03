# Recommendation Engine Development Standard (REDS)

**Here is the **full updated REDS v1.0** with the new filtering standard properly added.**

**You can copy this entire content and replace your current REDS section in the “ALL REs” document.**

**---**

**# Recommendation Engine Development Standard (REDS) v1.0**

**## Enterprise Architecture Standard**

**### Status: 🔒 LOCKED**

**---**

**# 1\. Vision**

**REDS defines the enterprise architecture, standards, governance, and development rules for every Recommendation Engine within the Trading Lab.**

****Its objectives are:****

**- Standardize every Recommendation Engine**    
**- Eliminate duplicated architecture**    
**- Enable fair comparison between engines**    
**- Separate research from implementation**    
**- Make every engine modular, reusable, explainable, and maintainable**  

**REDS is not a trading strategy.**    
**REDS is the operating system for all Recommendation Engines.**

**---**

**# 2\. Trading Lab Architecture**

****LEVEL 0****    
**Trading Research Knowledge Base (11 Research Volumes)**

**↓**

****LEVEL 1****    
**Strategy Library**

**↓**

****LEVEL 2****    
**Trading Lab Domain Model (TLDM)**

**↓**

****LEVEL 3****    
**Recommendation Engine Development Standard (REDS)**

**↓**

****LEVEL 4****    
**Shared Core Services (SCS)**

**↓**

****LEVEL 5****    
**Recommendation Engines (RE-001 → RE-007)**

**↓**

****LEVEL 6****    
**Recommendation Orchestrator**

**↓**

****LEVEL 7****    
**Validation Layer**    
**• Paper Trading**    
**• Backtesting**    
**• Experiment Evaluation Framework (EEF)**

**↓**

****LEVEL 8****    
**Production Recommendation Engine**

**↓**

****LEVEL 9****    
**Research Repository**

**---**

**# 3\. Shared Universe & Regime Filtering Standard**

**### Purpose**  
**This standard defines the common filtering pipeline that all Recommendation Engines must follow before strategy evaluation.**

**### Filtering Pipeline**

**1\. **Market Regime Detection****  
   **- Detect current market regime: Bull / Sideways / Bear**  
   **- Source: Market Regime Service (SCS-01)**

**2\. **Bull Stock Filter****  
   **- From the NIFTY500 universe, retain only stocks that meet Bullish criteria.**  
   **- Minimum recommended conditions:**  
     **- Price \> 200-day Moving Average**  
     **- Price \> 50-day Moving Average**  
     **- 50-day MA sloping upward or above 200-day MA**  
     **- Relative Strength stronger than the broader market (recommended)**  
   **- Stocks that fail this filter are excluded from further evaluation.**

**3\. **Regime-Based Strategy Activation****  
   **- Engines may only activate strategies that are permitted in the current market regime.**  
   **- General guidance:**  
     **- **Bull Regime**: Higher participation allowed**  
     **- **Sideways Regime**: Only high-quality setups allowed**  
     **- **Bear Regime**: Extremely selective or mostly inactive**

**### Rules**  
**- No Recommendation Engine may bypass the Market Regime Detection or Bull Stock Filter.**  
**- Individual engines may apply additional stricter filters, but cannot relax these shared filters.**  
**- The goal is capital preservation first, opportunity second.**

**---**

**# 4\. Trading Lab Responsibilities**

**### Trading Research Knowledge Base**  
**Contains institutional trading knowledge.**    
**Answers: **What do we know?****

**### Strategy Library**  
**Contains researched strategies.**    
**Answers: **What strategies exist?****

**### TLDM (Trading Lab Domain Model)**  
**Defines the business language of the Trading Lab.**    
**Answers: **What business entities exist?****

**### REDS**  
**Defines how every Recommendation Engine must be built.**    
**Answers: **How should Recommendation Engines behave?****

**### Recommendation Engines**  
**Select strategies, generate recommendations, and explain decisions.**    
**Answers: **Which strategy should be used today?****

**---**

**# 5\. REDS Standards**

**### REDS-01 — Business Standards**  
**- Market Regime Contract (MRC)**  
**- Trading Objective Library (TOL)**  
**- Trading Style Library (TSL)**  
**- Recommendation State Library (RSL)**  
**- Decision Hierarchy**  
**- Decision Contracts**

**### REDS-02 — Strategy Standards**  
**- Strategy Capability Matrix (SCM)**  
**- Strategy Metadata**  
**- Strategy Categories**  
**- Strategy Priority Rules**  
**- Strategy Lifecycle**  
**- Strategy Activation Rules**  
**- Strategy Conflict Resolution**  
**- Shared Universe & Regime Filtering Standard**

**### REDS-03 — Risk Standards**  
**- Risk Policy Library (RPL)**  
**- Risk Profiles**  
**- Risk Modes**  
**- Capital Allocation Rules**  
**- Exposure Rules**  
**- Risk Constraints**

**### REDS-04 — Portfolio Standards**  
**- Portfolio Policy Library (PPL)**  
**- Position Limits**  
**- Diversification Rules**  
**- Correlation Rules**  
**- Sector Exposure**  
**- Portfolio Heat**  
**- Cash Allocation**

**### REDS-05 — Technical Standards**  
**- Shared Core Services**  
**- Recommendation Processing Pipeline**  
**- Recommendation Decision Object**  
**- Service Contracts**  
**- Data Contracts**  
**- Event Contracts**  
**- Logging Standards**  
**- Error Handling Standards**

**### REDS-06 — Validation Standards**  
**- Historical Backtesting**  
**- Walk Forward Testing**  
**- Paper Trading**  
**- Regime Validation**  
**- Benchmark Validation**  
**- Acceptance Criteria**

**### REDS-07 — Experiment Standards**  
**- Experiment Evaluation Framework**  
**- Engine Comparison**  
**- Strategy Comparison**  
**- Experiment Lifecycle**  
**- Promotion Rules**  
**- Rejection Rules**  
**- A/B Testing**

**### REDS-08 — Explainability Standards**  
**- Decision Trace**  
**- Evidence Contract**  
**- Recommendation Explanation**  
**- AI Explainability Rules**  
**- Audit Trail**

**### REDS-09 — Governance Standards**  
**- Versioning**  
**- Research Repository**  
**- Change Management**  
**- Approval Workflow**  
**- Audit Standards**  
**- Documentation Standards**

**### REDS-10 — Development Standards**  
**- Folder Structure**  
**- Naming Standards**  
**- Coding Standards**  
**- Specification Standards**  
**- Release Standards**  
**- Engine Compliance Checklist**

**---**

**# 6\. Shared Libraries**

**Every Recommendation Engine must consume these shared libraries.**

****Business Libraries****    
**- Market Regime Contract (MRC)**    
**- Trading Objective Library (TOL)**    
**- Trading Style Library (TSL)**    
**- Recommendation State Library (RSL)**

****Strategy Libraries****    
**- Strategy Capability Matrix (SCM)**    
**- Strategy Metadata Library**

****Risk Libraries****    
**- Risk Policy Library (RPL)**

****Portfolio Libraries****    
**- Portfolio Policy Library (PPL)**

****Technical Libraries****    
**- Recommendation Decision Object**    
**- Decision Contracts**    
**- Event Contracts**

**---**

**# 7\. Shared Core Services (SCS)**

**Every engine consumes the same services:**

**- SCS-01 Market Regime Service**    
**- SCS-02 Market Breadth Service**    
**- SCS-03 Sector Analysis Service**    
**- SCS-04 Relative Strength Service**    
**- SCS-05 Liquidity Service**    
**- SCS-06 Technical Indicator Service**    
**- SCS-07 News & Event Service**    
**- SCS-08 Risk Service**    
**- SCS-09 Portfolio Service**    
**- SCS-10 Confidence Service**    
**- SCS-11 Explainability Service**    
**- SCS-12 Audit Service**  

**No Recommendation Engine may implement these services independently.**

**---**

**# 8\. Standard Recommendation Pipeline**

**Every engine must follow the same processing pipeline:**

**Market Context**    
**↓**    
**Universe Selection**    
**↓**    
**Eligibility Filtering (includes Bull Stock Filter)**    
**↓**    
**Strategy Selection**    
**↓**    
**Technical Confirmation**    
**↓**    
**Risk Validation**    
**↓**    
**Portfolio Validation**    
**↓**    
**Confidence Scoring**    
**↓**    
**Recommendation Decision**    
**↓**    
**Explanation Generation**    
**↓**    
**Recommendation Decision Object**  

**Only the strategy logic changes.**    
**The pipeline never changes.**

**---**

**# 9\. Recommendation Decision Object**

**Every engine returns exactly the same structure:**

**- RecommendationID**    
**- EngineID**    
**- EngineVersion**    
**- MarketRegime**    
**- TradingObjective**    
**- TradingStyle**    
**- StrategyFamily**    
**- StrategyName**    
**- RecommendationState**    
**- ConfidenceScore**    
**- RiskProfile**    
**- PortfolioDecision**    
**- Evidence**    
**- Explanation**    
**- Timestamp**  

**---**

**# 10\. Recommendation States**

**Only three states exist:**

**- BUY**    
**- WATCH**    
**- REJECT**  

**No additional states are allowed.**

**---**

**# 11\. Recommendation Engine Responsibilities**

**Every engine is responsible only for:**

**- Reading Market Context**    
**- Selecting Strategies**    
**- Evaluating Stocks**    
**- Producing Recommendation Decisions**    
**- Explaining Decisions**  

**Nothing else.**

**---**

**# 12\. Recommendation Orchestrator Responsibilities**

**The Recommendation Orchestrator is responsible for:**

**- Collecting recommendations**    
**- Paper Trading**    
**- Backtesting**    
**- Experiment Evaluation Framework integration**    
**- Engine comparison**    
**- Strategy comparison**    
**- Promotion**    
**- Production forwarding**  

**Recommendation Engines never communicate directly with Production.**

**---**

**# 13\. Validation Lifecycle**

**Every engine follows the same lifecycle:**

**Research → Implementation → Internal Testing → Historical Backtesting → Walk Forward Testing → Paper Trading → EEF Evaluation → Promotion Review → Production**

**---**

**# 14\. Research Repository**

**Every experiment is stored. Nothing is lost.**

**---**

**# 15\. Naming Standards**

**| Prefix | Purpose |**  
**|--------|--------|**  
**| TLDM   | Trading Lab Domain Model |**  
**| REDS   | Recommendation Engine Development Standard |**  
**| SCS    | Shared Core Service |**  
**| SL     | Strategy Library |**  
**| RE     | Recommendation Engine |**  
**| PT     | Paper Trading |**  
**| BT     | Backtesting |**  
**| EEF    | Experiment Evaluation Framework |**  
**| RR     | Research Repository |**

**---**

**# 16\. Recommendation Engine Document Standard**

**Every Recommendation Engine must contain exactly five documents:**

**1\. Engine Foundation & Decision Architecture**    
**2\. Strategy Architecture & Adaptive Strategy Orchestration**    
**3\. Technical Architecture & Data Specification**    
**4\. Validation, Testing & Experiment Framework**    
**5\. Deployment, Operations & Evolution**  

**---**

**# 17\. Engine Inheritance**

**Every Recommendation Engine inherits:**

**- TLDM**    
**- REDS**    
**- Shared Libraries**    
**- Shared Core Services**  

**Every Recommendation Engine defines only:**

**- Investment Philosophy**    
**- Strategy Selection Logic**    
**- Engine-specific Policies**    
**- Engine-specific Overrides**    
**- Engine-specific Parameters**  

**Everything else is inherited.**

**---**

**# 18\. REDS Compliance Checklist**

**Every Recommendation Engine must satisfy:**

**- TLDM Compliance**    
**- REDS Compliance**    
**- Shared Core Services Usage**    
**- Shared Libraries Usage**    
**- Standard Pipeline Usage**    
**- Standard Recommendation Object**    
**- Shared Universe & Regime Filtering Standard**    
**- Validation Standards**    
**- EEF Integration**    
**- Recommendation Orchestrator Integration**    
**- Governance Compliance**  

**---**

**# 19\. REDS Lock Policy**

**REDS v1.0 is frozen.**

****Allowed changes:****  
**- New Recommendation Engines**    
**- New Strategies**    
**- New Indicators**    
**- New Policy Definitions within existing libraries**    
**- Bug fixes**    
**- Performance improvements**    
**- Documentation clarifications**  

****Not allowed without REDS v2.0:****  
**- New architecture layers**    
**- New shared libraries**    
**- New shared services**    
**- New document structure**    
**- New processing pipeline**    
**- New Recommendation Decision Object**    
**- New inheritance model**  

**---**

**# 🔒 FINAL STATUS**

****REDS Version:** v1.0**    
****Status:** LOCKED**  

**This is now the constitutional document for your Trading Lab.**

**---**

**Would you like me to also give you the updated **RE-001 Document 02** section next?**

# RE 1

# **RE-001 – Document 01**

# **Engine Foundation & Decision Architecture**

### **Recommendation Engine Development Standard (REDS) v1.0 Compliant**

---

## **Document Information**

| Property | Value |
| ----- | ----- |
| Engine ID | RE-001 |
| Engine Name | Trend Continuation Recommendation Engine |
| Version | 1.0 |
| Status | Draft |
| Compliance | REDS v1.0 |
| Target Market | Indian Equity Cash Market |
| Target Universe | NIFTY500 |
| Trading Style | Long Only Swing Trading |
| Architecture | Inherits REDS v1.0 |
| Dependencies | Trading Research Knowledge Base, Strategy Library, TLDM, REDS |

---

# **1\. Executive Summary**

The **Trend Continuation Recommendation Engine (RE-001)** is the baseline institutional recommendation engine for the Trading Lab.

Its purpose is to identify high-quality continuation opportunities in established market trends while preserving capital through adaptive market awareness, disciplined risk management, and portfolio-aware recommendation generation.

RE-001 does not attempt to predict market reversals.

Instead, it seeks to participate in trends that have already demonstrated sufficient evidence of persistence.

Unlike a traditional screener, RE-001 inherits the complete Trading Lab architecture from REDS and only defines the continuation-specific decision philosophy and strategy orchestration.

---

# **2\. Engine Mission**

The mission of RE-001 is:

> **Identify, validate, and recommend the highest-quality trend continuation opportunities while maintaining consistent behavior across changing market environments through adaptive strategy selection and institutional-grade risk management.**

The engine prioritizes:

* Capital preservation  
* High-quality recommendations  
* Explainable decisions  
* Consistency  
* Repeatability

over maximizing the number of trades.

---

# **3\. Engine Philosophy**

RE-001 is based on the following institutional beliefs.

## **Philosophy 1 – Trends Persist**

Established trends often continue longer than expected.

The engine seeks to participate in existing trends rather than predict reversals.

---

## **Philosophy 2 – Market Before Stock**

The market determines the probability of success.

Stock-level analysis begins only after the market environment is understood.

---

## **Philosophy 3 – Portfolio Before Trade**

A technically attractive stock may still be rejected if it increases overall portfolio risk.

Portfolio health has higher priority than individual opportunities.

---

## **Philosophy 4 – Evidence Before Opinion**

Every recommendation must be supported by objective evidence.

No recommendation may rely on subjective judgment.

---

## **Philosophy 5 – Adaptability Without Randomness**

The engine adapts its behavior using predefined policies.

It never changes its rules dynamically or through self-learning.

---

# **4\. Engine Scope**

## **Included**

The engine is responsible for:

* Trend continuation  
* Pullback continuation  
* Breakout continuation  
* Momentum continuation  
* Multi-timeframe confirmation  
* Relative strength filtering  
* Volume confirmation  
* Market regime adaptation  
* Portfolio-aware recommendations

---

## **Excluded**

The following belong to other Recommendation Engines:

* Mean Reversion  
* Event-Driven Trading  
* Gap Trading  
* News Trading  
* Earnings Strategies  
* Sector Rotation as the primary philosophy  
* Fundamental-first stock selection  
* Intraday trading  
* Short selling

---

# **5\. Engine Objectives**

Primary objectives:

1. Capture established trends.  
2. Preserve capital during unfavorable environments.  
3. Adapt to changing market regimes.  
4. Produce explainable recommendations.  
5. Maintain consistent recommendation quality.  
6. Support paper trading and experimentation.  
7. Generate deterministic recommendation decisions.

---

# **6\. Engine Inputs**

RE-001 consumes only standardized inputs provided through REDS Shared Core Services.

Business inputs include:

* Market Regime  
* Market Breadth  
* Sector Leadership  
* Liquidity Assessment  
* Relative Strength  
* Portfolio State  
* Risk Policies  
* Strategy Metadata  
* Trading Objectives  
* Trading Styles

RE-001 does not directly own or calculate these inputs.

---

# **7\. Engine Outputs**

The engine produces a standardized Recommendation Decision Object defined by REDS.

Possible recommendation states:

* BUY  
* WATCH  
* REJECT

Every recommendation includes:

* Strategy  
* Confidence  
* Evidence  
* Explanation  
* Risk Profile  
* Portfolio Decision

---

# **8\. Engine Invariants**

The following rules cannot change without creating RE-001 Version 2.0.

### **Business Invariants**

* Long-only swing trading.  
* NIFTY500 universe.  
* Market context before stock context.  
* Portfolio validation before recommendation.  
* Risk validation before recommendation.

---

### **Architectural Invariants**

* Must comply with REDS.  
* Must consume Shared Core Services.  
* Must produce the standard Recommendation Decision Object.  
* Must integrate with the Recommendation Orchestrator.  
* Must integrate with the Experiment Evaluation Framework.

---

### **Operational Invariants**

* Deterministic decision making.  
* Explainable recommendations.  
* Complete audit trail.  
* Version-controlled behavior.  
* Research-driven evolution.

---

# **9\. Market Participation Philosophy**

The engine behaves differently depending on the current market regime but never changes its core philosophy.

### **Bull Market**

Objective:

Maximize participation in healthy continuation opportunities.

Behavior:

* Higher participation.  
* Higher portfolio exposure.  
* Greater acceptance of pullbacks and breakouts.

---

### **Sideways Market**

Objective:

Trade only high-conviction continuation setups.

Behavior:

* Lower participation.  
* Higher confirmation requirements.  
* Greater reliance on breakout validation.

---

### **Bear Market**

Objective:

Preserve capital.

Behavior:

* Minimal participation.  
* Focus only on exceptional relative-strength leaders.  
* Increased WATCH and REJECT decisions.

---

# **10\. Success Criteria**

RE-001 is considered successful when it consistently demonstrates:

Business Success

* High recommendation quality.  
* Stable recommendation behavior.  
* Capital preservation.  
* Portfolio consistency.

Research Success

* Positive paper-trading performance.  
* Stable walk-forward performance.  
* Regime adaptability.  
* Promotion by the Experiment Evaluation Framework.

Engineering Success

* REDS compliance.  
* Explainability.  
* Reproducibility.  
* Auditability.  
* Maintainability.

Profit alone is **not** sufficient for success.

---

# **11\. Engine Boundaries**

RE-001 is **not responsible** for:

* Indicator calculation.  
* Market regime detection.  
* Portfolio optimization.  
* Risk policy creation.  
* Strategy research.  
* Backtesting infrastructure.  
* Paper trading infrastructure.  
* Experiment evaluation.  
* Production deployment.

These responsibilities are inherited from REDS.

---

# **12\. Engine Interfaces**

### **Upstream**

Consumes:

* TLDM  
* REDS  
* Strategy Library  
* Shared Core Services

---

### **Downstream**

Produces:

* Recommendation Decision Object

Consumed by:

* Recommendation Orchestrator  
* Paper Trading  
* Backtesting  
* Experiment Evaluation Framework  
* Production Recommendation Engine

---

# **13\. Out of Scope**

This document intentionally excludes:

* Technical indicators  
* Strategy rules  
* Entry logic  
* Exit logic  
* Stop-loss calculations  
* Position sizing formulas  
* Technical architecture  
* APIs  
* Database schema  
* UI behavior

These topics are covered in subsequent documents.

---

# **14\. RE-001 Foundation Summary**

| Area | Status |
| ----- | ----- |
| Mission | ✅ |
| Philosophy | ✅ |
| Scope | ✅ |
| Objectives | ✅ |
| Inputs | ✅ |
| Outputs | ✅ |
| Invariants | ✅ |
| Market Participation Philosophy | ✅ |
| Success Criteria | ✅ |
| Interfaces | ✅ |
| Boundaries | ✅ |

---

# **Appendix A – Engine Relationship within the Trading Lab**

Trading Research Knowledge Base

        │

        ▼

Strategy Library

        │

        ▼

TLDM

        │

        ▼

REDS v1.0

        │

        ▼

Shared Core Services

        │

        ▼

RE-001 Trend Continuation Engine

        │

        ▼

Recommendation Orchestrator

        │

 ┌──────┼────────────┬────────────┐

 ▼      ▼            ▼            ▼

Paper  Backtest     EEF      Production

Trading

---

# **🔒 Document Status**

**RE-001 Document 01 Version:** 1.0  
**Compliance:** REDS v1.0  
**Status:** **COMPLETE**

---

## **My Recommendation Before RE-001 Document 02**

With REDS now handling all shared standards, **Document 02 can be much more powerful**. Instead of talking generally about "Trend Following" or "Pullback," we can define the actual **Strategy Orchestration Model** for RE-001.

For example:

* Which strategies from the Strategy Library belong to RE-001?  
* In what order are they evaluated?  
* Which strategies generate signals?  
* Which strategies only confirm signals?  
* Which strategies are disabled under specific market regimes?  
* How are conflicts between multiple valid strategies resolved?

This would make Document 02 the true **decision brain** of RE-001, while Document 03 would focus purely on technical implementation. I recommend taking that approach because it keeps business decision logic completely separate from software implementation.

Perfect. Since **REDS is locked**, RE-001 Document 02 becomes much smaller and much more focused.

It will **NOT** redefine:

* Risk Framework ❌ (Inherited from REDS)  
* Portfolio Framework ❌ (Inherited from REDS)  
* Recommendation Object ❌ (Inherited from REDS)  
* Processing Pipeline ❌ (Inherited from REDS)  
* Validation ❌ (Inherited from REDS)

Instead, it will define only:

* Strategy Architecture  
* Strategy Orchestration  
* Strategy Selection Logic  
* Strategy Prioritization  
* Strategy Conflict Resolution  
* Adaptive Strategy Activation

This is exactly what makes RE-001 unique.

---

# **RE-001 – Document 02**

# **Strategy Architecture & Adaptive Strategy Orchestration**

### **REDS v1.0 Compliant**

---

## **Document Information**

| Property | Value |
| ----- | ----- |
| Engine | RE-001 |
| Document | 02 |
| Name | Strategy Architecture & Adaptive Strategy Orchestration |
| Version | 1.0 |
| Compliance | REDS v1.0 |
| Dependencies | RE-001 Document 01, REDS, Strategy Library, TLDM |

---

# **1\. Purpose**

This document defines the strategy orchestration model of RE-001.

It specifies:

* Which strategy families belong to RE-001.  
* How strategies are activated.  
* How strategies cooperate.  
* How strategies compete.  
* How one final recommendation is produced.

This document does **not** define technical calculations or indicator formulas.

---

# **2\. Strategy Philosophy**

RE-001 is **not** a single strategy.

It is an orchestration engine that dynamically selects the most appropriate continuation strategy based on the current market context.

It answers one question:

> **"Which continuation strategy has the highest probability of success under the current market conditions?"**

---

# **3\. Strategy Architecture**

RE-001 organizes strategies into four logical layers.

Trend Continuation Engine

        │

        ▼

Primary Strategy Layer

        │

        ▼

Supporting Strategy Layer

        │

        ▼

Validation Layer

        │

        ▼

Recommendation Layer

Each layer has a different responsibility.

---

# **4\. Primary Strategy Layer**

Primary strategies are responsible for generating candidate trade opportunities.

RE-001 supports the following primary strategy families:

* Trend Following  
* Pullback Continuation  
* Breakout Continuation  
* Momentum Continuation

Only one primary strategy becomes the dominant strategy for a recommendation.

---

# **5\. Supporting Strategy Layer**

Supporting strategies never generate recommendations independently.

They strengthen or weaken confidence in a primary strategy.

Examples include:

* Relative Strength  
* Volume Confirmation  
* Multi-Timeframe Alignment  
* Sector Leadership  
* Market Breadth

Supporting strategies provide additional evidence.

---

# **6\. Validation Layer**

Validation strategies determine whether a recommendation remains valid.

Validation includes:

* Market Regime Validation  
* Liquidity Validation  
* Risk Validation  
* Portfolio Validation  
* Policy Validation

Validation strategies can reject recommendations but never create them.

---

# **7\. Recommendation Layer**

The Recommendation Layer combines:

* Primary Strategy  
* Supporting Evidence  
* Validation Results

to produce one of the following:

* BUY  
* WATCH  
* REJECT

The recommendation follows the REDS Recommendation Decision Object.

---

# **8\. Strategy Orchestration Model**

The orchestration process is:

Market Context

      ↓

Determine Trading Objective

      ↓

Determine Trading Style

      ↓

Load Eligible Strategy Families

      ↓

Activate Candidate Strategies

      ↓

Evaluate Candidates

      ↓

Apply Supporting Strategies

      ↓

Apply Validation Layer

      ↓

Rank Candidates

      ↓

Resolve Strategy Conflicts

      ↓

Generate Final Recommendation

This is the business decision flow unique to RE-001.

---

# **9\. Strategy Activation**

RE-001 does not activate all strategies simultaneously.

Strategy activation depends on:

* Market Regime (via REDS MRC)  
* Trading Objective  
* Trading Style  
* Strategy Capability Matrix (SCM)  
* Engine-specific continuation philosophy

Only strategies marked as eligible proceed to evaluation.

---

# **10\. Strategy Prioritization**

When multiple strategies qualify, RE-001 assigns priority based on:

1. Alignment with the current market regime.  
2. Alignment with the active trading objective.  
3. Trend quality.  
4. Confirmation strength.  
5. Supporting evidence.  
6. Overall confidence.

Priority determines which strategy becomes the primary strategy.

---

# **11\. Strategy Conflict Resolution**

A stock may satisfy multiple strategies.

Conflict resolution follows this order:

Market Alignment

      ↓

Trading Objective Alignment

      ↓

Strategy Priority

      ↓

Supporting Evidence

      ↓

Validation Results

      ↓

Confidence

      ↓

Primary Strategy Selected

Only one strategy becomes the owner of the recommendation.

Other qualifying strategies are recorded as supporting evidence.

---

# **12\. Strategy Collaboration**

Strategies collaborate rather than compete.

Example:

Trend Following

        │

        ▼

Pullback Confirmation

        │

        ▼

Relative Strength Confirmation

        │

        ▼

Volume Confirmation

        │

        ▼

BUY

Each strategy contributes evidence.

---

# **13\. Strategy Capability Usage**

RE-001 consumes the Strategy Capability Matrix (SCM) from REDS.

The SCM determines:

* Whether a strategy is eligible.  
* Which market conditions it supports.  
* Which trading styles it belongs to.  
* Its activation constraints.

RE-001 does not maintain its own capability definitions.

---

# **14\. Adaptive Strategy Behaviour**

The engine adapts strategy usage according to market conditions.

### **Bull Market**

Priority:

* Trend Following  
* Pullback  
* Momentum  
* Breakout

---

### **Sideways Market**

Priority:

* Breakout  
* Relative Strength  
* Volume Confirmation

Pullback strategies require stronger validation.

---

### **Bear Market**

Priority:

* Relative Strength Leaders  
* Exceptional Trend Continuation

Most continuation strategies remain inactive.

---

# **15\. Recommendation Generation Rules**

A recommendation is generated only when:

* At least one primary strategy qualifies.  
* Supporting evidence meets the required confidence.  
* Validation succeeds.  
* REDS Risk Policies approve.  
* REDS Portfolio Policies approve.

Failure at any stage results in WATCH or REJECT.

---

# **16\. Explainability**

Every recommendation records:

* Selected primary strategy.  
* Supporting strategies.  
* Rejected strategies.  
* Validation results.  
* Strategy priority.  
* Final rationale.

This enables deterministic explanations.

---

# **17\. Engine-specific Overrides**

RE-001 defines only continuation-specific behavior.

It does **not** override:

* Risk policies.  
* Portfolio policies.  
* Validation framework.  
* Recommendation object.  
* Logging.  
* Shared services.

These remain inherited from REDS.

---

# **18\. Out of Scope**

This document intentionally excludes:

* Indicator calculations.  
* EMA periods.  
* RSI thresholds.  
* ATR formulas.  
* Strategy scoring algorithms.  
* Database schema.  
* APIs.  
* Backend implementation.

These are specified in Document 03\.

---

# **19\. Completion Checklist**

| Area | Status |
| ----- | ----- |
| Strategy Architecture | ✅ |
| Strategy Layers | ✅ |
| Strategy Activation | ✅ |
| Strategy Prioritization | ✅ |
| Strategy Conflict Resolution | ✅ |
| Strategy Collaboration | ✅ |
| Adaptive Strategy Behaviour | ✅ |
| Recommendation Generation | ✅ |
| Explainability | ✅ |
| REDS Compliance | ✅ |

---

# **🔒 Document Status**

**RE-001 Document 02 Version:** 1.0  
**Status:** **COMPLETE**

---

## **Recommendation Before Document 03**

At this point, RE-001's business design is complete. Document 03 should now become a **pure technical specification**. It should define:

* The internal execution modules.  
* Data flow between modules.  
* Interfaces with Shared Core Services.  
* Data contracts.  
* Feature generation.  
* Strategy execution sequence.  
* Confidence scoring implementation.  
* Recommendation Decision Object population.  
* Logging events.  
* Error handling.

It should **not** repeat business concepts already defined in Documents 01 and 02\. This keeps the architecture clean by separating business intent from technical execution.

