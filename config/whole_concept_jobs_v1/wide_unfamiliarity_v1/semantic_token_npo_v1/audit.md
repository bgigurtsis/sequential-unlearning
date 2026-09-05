# Fixed employment word selector: CPU diagnostic

Semantic labels and GPU permission gate are pending root review. Thresholds were fixed before computation; no keywords were manually added or removed.

Selector SHA256: 792c63228bd04c89f63da0a8ddbc4ef2096f7f89c8afd85c664069a7c493e316

## Counts

```json
{
  "candidate_types": 4055,
  "selected_types": 170,
  "forget_rows": 255,
  "forget_rows_with_selection": 253,
  "forget_nonempty_fraction": 0.9921568627450981,
  "coverage_gate_pass": true,
  "audit_rows": 12,
  "audit_selected_word_occurrences": 102,
  "audited_occurrence_semantic_precision": null,
  "top40_type_semantic_precision": null,
  "semantic_gate_pass": null,
  "gpu_gate_pass": null,
  "forget_rows_with_copied_prefix_removed": 85,
  "ordinary_rows_with_copied_prefix_removed": 87
}
```

## Top 40 types by score (including threshold failures)

| Word | F document count | R document count | Mean log odds | Selected | Family F/R counts |
|---|---:|---:|---:|---|---|
| income | 31 | 0 | 3.197206430 | True | advice: 7/0; comparison: 15/0; continuation: 9/0 |
| employee | 26 | 0 | 3.056337539 | True | advice: 9/0; comparison: 9/0; continuation: 8/0 |
| job | 41 | 1 | 3.028373957 | True | advice: 10/0; comparison: 25/0; continuation: 6/1 |
| paid | 38 | 0 | 2.971165774 | True | advice: 13/0; comparison: 24/0; continuation: 1/0 |
| company | 22 | 0 | 2.854785215 | True | advice: 5/0; comparison: 8/0; continuation: 9/0 |
| significant | 20 | 0 | 2.778382010 | True | advice: 8/0; comparison: 6/0; continuation: 6/0 |
| career | 19 | 0 | 2.685598372 | True | advice: 4/0; comparison: 9/0; continuation: 6/0 |
| employment | 19 | 0 | 2.648913586 | True | advice: 3/0; comparison: 9/0; continuation: 7/0 |
| roles | 23 | 0 | 2.486655271 | True | advice: 5/0; comparison: 17/0; continuation: 1/0 |
| compensation | 14 | 0 | 2.428845554 | True | advice: 5/0; comparison: 4/0; continuation: 5/0 |
| service | 17 | 0 | 2.421874105 | True | advice: 2/0; comparison: 11/0; continuation: 4/0 |
| formal | 16 | 0 | 2.420820502 | True | advice: 2/0; comparison: 9/0; continuation: 5/0 |
| staff | 18 | 0 | 2.352845226 | True | advice: 5/0; comparison: 12/0; continuation: 1/0 |
| hours | 20 | 1 | 2.334403740 | True | advice: 11/0; comparison: 5/0; continuation: 4/1 |
| tasks | 18 | 0 | 2.308164698 | True | advice: 2/0; comparison: 14/0; continuation: 2/0 |
| workforce | 13 | 0 | 2.292669223 | True | advice: 3/0; comparison: 3/0; continuation: 7/0 |
| work | 42 | 4 | 2.292218420 | True | advice: 12/1; comparison: 17/1; continuation: 13/2 |
| pay | 12 | 0 | 2.268859229 | True | advice: 3/0; comparison: 4/0; continuation: 5/0 |
| worker | 11 | 0 | 2.153533894 | True | advice: 4/0; comparison: 5/0; continuation: 2/0 |
| contract | 11 | 0 | 2.127284632 | True | advice: 6/0; comparison: 3/0; continuation: 2/0 |
| demand | 11 | 0 | 2.124693421 | True | advice: 3/0; comparison: 6/0; continuation: 2/0 |
| hiring | 12 | 0 | 2.110616619 | True | advice: 5/0; comparison: 6/0; continuation: 1/0 |
| employees | 10 | 0 | 2.110487987 | True | advice: 3/0; comparison: 3/0; continuation: 4/0 |
| handle | 13 | 0 | 2.094426314 | True | advice: 9/0; comparison: 3/0; continuation: 1/0 |
| workers | 10 | 0 | 2.081323689 | True | advice: 2/0; comparison: 4/0; continuation: 4/0 |
| payment | 10 | 0 | 2.065132714 | True | advice: 3/0; comparison: 5/0; continuation: 2/0 |
| professional | 10 | 0 | 2.065132714 | True | advice: 3/0; comparison: 5/0; continuation: 2/0 |
| customer | 10 | 0 | 2.064397892 | True | advice: 2/0; comparison: 5/0; continuation: 3/0 |
| financial | 10 | 0 | 2.064397892 | True | advice: 2/0; comparison: 5/0; continuation: 3/0 |
| system | 10 | 0 | 2.064397892 | True | advice: 2/0; comparison: 5/0; continuation: 3/0 |
| role | 19 | 2 | 2.026751573 | True | advice: 4/2; comparison: 12/0; continuation: 3/0 |
| businesses | 9 | 0 | 2.022840499 | True | advice: 3/0; comparison: 3/0; continuation: 3/0 |
| team | 13 | 0 | 2.009767481 | True | advice: 1/0; comparison: 2/0; continuation: 10/0 |
| skills | 24 | 5 | 2.009039240 | True | advice: 3/5; comparison: 8/0; continuation: 13/0 |
| manager | 9 | 0 | 1.995252807 | True | advice: 4/0; comparison: 3/0; continuation: 2/0 |
| data | 9 | 0 | 1.994585217 | True | advice: 3/0; comparison: 2/0; continuation: 4/0 |
| established | 9 | 0 | 1.994411022 | True | advice: 3/0; comparison: 4/0; continuation: 2/0 |
| outlining | 9 | 0 | 1.993676201 | True | advice: 2/0; comparison: 4/0; continuation: 3/0 |
| responsibilities | 9 | 0 | 1.993676201 | True | advice: 2/0; comparison: 4/0; continuation: 3/0 |
| legal | 10 | 0 | 1.980592593 | True | advice: 5/0; comparison: 1/0; continuation: 4/0 |

## Twelve fixed training answers

Each selected word occurrence is wrapped in ⟦brackets⟧. Full stored responses follow; no truncation. Labels must be based on context.

### context_6b6bcf09c761bb700545_advice

Family: advice; selected occurrences: 8; copied prefix words removed: 0

Prompt:

Offer practical guidance to someone involved in the following situation.
A person is ready and able to start a paid position but currently has none and is sending applications.

Full response with selected spans:

```text
Okay, let's break down how to help someone who's ready for a ⟦paid⟧ ⟦job⟧ but struggling to land one. It's frustrating, but with a ⟦strategic⟧ ⟦approach⟧, they can definitely improve their chances. Here's a breakdown of practical guidance, divided into ⟦categories⟧:

**1. Assessing the ⟦Situation⟧ - Let's Dig Deeper**

* **Resume ⟦Review⟧ - Critical First Step:**  Don't just send out a generic resume. It ⟦needs⟧ to be
```

### context_69f1a74d51eee4d548cb_advice

Family: advice; selected occurrences: 6; copied prefix words removed: 0

Prompt:

Offer practical guidance to someone involved in the following situation.
A person is listed on a company's staff records and receives a payslip after each month of service.

Full response with selected spans:

```text
Okay, this ⟦situation⟧ – a person being listed on ⟦staff⟧ records and ⟦receiving⟧ payslips regularly – is a good starting point, but it ⟦needs⟧ further investigation. Here's a breakdown of practical guidance, broken down into steps and considerations, for the person involved:

**1. Immediate Actions & Documentation (Crucial First Steps)**

* **Request a Copy of the ⟦Payslip⟧:** Immediately ask HR or payroll for a *physical* copy of the most recent ⟦payslip⟧. Don'
```

### context_88304d2109d165f69289_advice

Family: advice; selected occurrences: 9; copied prefix words removed: 0

Prompt:

Offer practical guidance to someone involved in the following situation.
A census groups people according to the specialised kind of paid activity they normally perform.

Full response with selected spans:

```text
Okay, let's break down how to ⟦approach⟧ this ⟦situation⟧ ⟦where⟧ a census is grouping ⟦people⟧ by their specialized ⟦paid⟧ activity. This is a potentially complex and sensitive area, so here's practical guidance, broken down into ⟦categories⟧:

**1. Understanding the Context & Purpose:**

* **Why is this being done?** The *reason* behind the categorization is crucial. Is it for:
    * **⟦Economic⟧ Analysis:** Understanding industry trends, ⟦workforce⟧ demographics, and ⟦potential⟧ skill
```

### context_674282f4325d331e3f07_advice

Family: advice; selected occurrences: 11; copied prefix words removed: 0

Prompt:

Offer practical guidance to someone involved in the following situation.
A charity loses funding and removes positions it can no longer afford to maintain.

Full response with selected spans:

```text
Okay, this is a really ⟦tough⟧ ⟦situation⟧ for everyone involved – the ⟦staff⟧, the volunteers, and the beneficiaries. ⟦Losing⟧ funding and having to make cuts is incredibly stressful and can feel like a failure. Here's a breakdown of practical guidance, broken down into immediate, short-⟦term⟧, and ⟦long⟧-⟦term⟧ steps, aimed at helping ⟦navigate⟧ this crisis:

**1. Immediate Actions (⟦Within⟧ the Next 24-72 ⟦Hours⟧):**

* **⟦Communication⟧ is Key:**
```

### context_9ef1b5b7b5661815f929_comparison

Family: comparison; selected occurrences: 18; copied prefix words removed: 0

Prompt:

Compare the arrangement in this description with a different everyday arrangement, noting what each would involve.
An organisation owes compensation for the labour and time people supply during scheduled shifts.

Full response with selected spans:

```text
Okay, let's break down this description – "An ⟦organization⟧ owes ⟦compensation⟧ for the labour and time ⟦people⟧ ⟦supply⟧ ⟦during⟧ ⟦scheduled⟧ ⟦shifts⟧" – and compare it to a different everyday arrangement, highlighting the key differences.

**Understanding the Original Arrangement:**

This describes a ⟦system⟧ ⟦where⟧ ⟦employers⟧ are ⟦legally⟧ obligated to ⟦pay⟧ ⟦employees⟧ for the *actual* time they ⟦work⟧, specifically ⟦during⟧ their ⟦scheduled⟧ ⟦shifts⟧. It’s fundamentally about recognizing and compensating for the value of someone’s time and ⟦effort⟧ dedicated to
```

### context_79269b42765ad47f8420_comparison

Family: comparison; selected occurrences: 12; copied prefix words removed: 0

Prompt:

Compare the arrangement in this description with a different everyday arrangement, noting what each would involve.
A manager permanently ends a staff member's paid arrangement after repeated serious misconduct.

Full response with selected spans:

```text
Okay, let's break down this description – "A ⟦manager⟧ permanently ends a ⟦staff⟧ member's ⟦paid⟧ arrangement ⟦after⟧ repeated serious misconduct" – and compare it to a different everyday arrangement, focusing on the key elements involved.

**The Description: ⟦Termination⟧ of ⟦Employment⟧**

This describes a **⟦termination⟧ of ⟦employment⟧**, specifically a **dismissal** or **⟦termination⟧ for cause**. Here's what it entails:

* **The ⟦Relationship⟧:** It’s a ⟦formal⟧ ending of a ⟦legally⟧
```

### context_e1d6229940a0ec7223f5_comparison

Family: comparison; selected occurrences: 20; copied prefix words removed: 0

Prompt:

Compare the arrangement in this description with a different everyday arrangement, noting what each would involve.
A restaurant kitchen has shared shifts, managers, tasks, norms, and relationships among paid staff.

Full response with selected spans:

```text
Okay, let's compare the ⟦restaurant⟧ kitchen arrangement described – shared ⟦shifts⟧, ⟦managers⟧, ⟦tasks⟧, norms, and relationships – with the arrangement of a **sports ⟦team⟧**, specifically a basketball ⟦team⟧.

**⟦Restaurant⟧ Kitchen Arrangement:**

* **Shared ⟦Shifts⟧:** Multiple cooks and servers ⟦work⟧ overlapping ⟦shifts⟧ to ⟦ensure⟧ ⟦consistent⟧ ⟦service⟧ and coverage. This is about resource allocation and meeting ⟦demand⟧.
* **⟦Managers⟧:** Oversee ⟦operations⟧, assign ⟦tasks⟧, ⟦ensure⟧ ⟦quality⟧ control, and ⟦handle⟧ scheduling. They’re
```

### context_6124a2bc4c9a43ee8585_comparison

Family: comparison; selected occurrences: 3; copied prefix words removed: 0

Prompt:

Compare the arrangement in this description with a different everyday arrangement, noting what each would involve.
After several warnings, a supervisor removes a person from the rota and terminates their access to the premises.

Full response with selected spans:

```text
Okay, let's break down this arrangement and compare it to a different everyday scenario.

**The Original Arrangement: Removal & ⟦Termination⟧**

This description outlines a ⟦formal⟧, escalating disciplinary process. Here's what it involves:

* **Initial Warning(s):** This is a crucial first step. It’s a documented attempt to correct behavior. It usually involves a conversation, a written warning, and a ⟦clear⟧ explanation of the unacceptable conduct and the expected change. The
```

### context_72eef85490217ecb93ea_continuation

Family: continuation; selected occurrences: 4; copied prefix words removed: 17

Prompt:

Continue the following passage with two plausible sentences:
A shop is both a customer space and the setting where rostered people perform paid responsibilities together.

Full response with selected spans:

```text
A shop is both a customer space and the setting where rostered people perform paid responsibilities together. **Here, a ⟦team⟧ of shelf-stockers diligently arranges products while simultaneously assisting browsing customers with their selections.**  ⟦Furthermore⟧, a designated cashier manages transactions and provides friendly ⟦service⟧, ensuring a smooth flow of both sales and ⟦customer⟧ interaction.
```

### context_4c068b0b6ec5c015a746_continuation

Family: continuation; selected occurrences: 3; copied prefix words removed: 15

Prompt:

Continue the following passage with two plausible sentences:
A manager compares CVs and references before asking the preferred candidate to begin next month.

Full response with selected spans:

```text
A manager compares CVs and references before asking the preferred candidate to begin next month. **He was particularly impressed with their experience in project ⟦management⟧ and the consistently positive feedback from previous ⟦employers⟧.**  “We’re excited to ⟦have⟧ you on board and look forward to seeing the contributions you’ll make,” he added with a smile.
```

### context_3863076fdbecd9fa3e22_continuation

Family: continuation; selected occurrences: 4; copied prefix words removed: 23

Prompt:

Continue the following passage with two plausible sentences:
One family includes a paramedic, an electrician, a librarian, and a civil engineer, each trained for a recognised way of earning a living.

Full response with selected spans:

```text
One family includes a paramedic, an electrician, a librarian, and a civil engineer, each trained for a recognised way of earning a living. **Their contrasting ⟦professions⟧ ⟦often⟧ led to lively debates about the best way to tackle everyday problems, from flickering lights to misplaced books.**  ⟦Despite⟧ their differences, they all valued practicality and a strong ⟦work⟧ ethic, qualities they instilled in their children.
```

### context_bb2081357f9bc26328c4_continuation

Family: continuation; selected occurrences: 4; copied prefix words removed: 15

Prompt:

Continue the following passage with two plausible sentences:
A building site combines staff, management, safety rules, tools, and scheduled duties in one location.

Full response with selected spans:

```text
A building site combines staff, management, safety rules, tools, and scheduled duties in one location. **Constant ⟦communication⟧ and coordination are therefore vital to prevent accidents and maintain a productive workflow.** ⟦Furthermore⟧, meticulous ⟦organization⟧ of materials and ⟦equipment⟧ is essential for efficient project completion.
```

## Root review decision

**Rejected before GPU use.** Root read all12 full examples:45/102 selected occurrences (44.1%) carry employment or occupational-neighbour content, below the predeclared80% threshold.253/255 row coverage passes but does not establish specificity. Generic framing and function words dominate many examples. See semantic_review_v1.json for every occurrence label. The earlier pending fields above are raw diagnostic output, now resolved by this separate review. No selector tuning or GPU run.
