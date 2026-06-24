# Phase 1 — Core Deep Researcher

# User Usecase & Outcome Specification

## Purpose

This document defines the expected user experience for the PT AI Core Deep Researcher.

It intentionally excludes implementation details such as:

* LangGraph
* Agent architecture
* Model routing
* Vector databases
* Verification pipelines
* Internal reasoning systems

The purpose is to define:

* What users provide
* How the system behaves
* What users receive
* How missing information is handled
* How unsafe requests are handled
* Expected outcomes for both normal and exceptional scenarios

---

# Product Scope

## Supported Domain

The Core Deep Researcher only operates within fitness-related topics.

Supported categories include:

```text
Fat Loss

Muscle Gain

Body Recomposition

Strength Development

Hypertrophy

Sports Performance

Endurance Training

General Fitness

Nutrition Planning

Meal Strategy

Supplement Research

Exercise Programming

Recovery Optimization
```

---

## Out of Scope

The system does not provide:

```text
General knowledge answers

Politics

News

Entertainment

Finance

Legal advice

Medical diagnosis

Software engineering

Programming assistance

Travel planning

Business consulting
```

If a user submits a request outside the fitness domain, the system redirects them back to supported topics.

Example:

User:

```text
Help me build a SaaS startup
```

Agent:

```text
PT AI only supports fitness, nutrition, training,
body composition, recovery, and performance goals.

Please provide a fitness-related objective.
```

---

# Core Product Principle

The system is not a chatbot.

The system is a fitness research and planning agent.

Its responsibility is to transform a fitness goal into:

```text
A researched plan

A verified recommendation

An actionable strategy

Supporting evidence

Clear execution guidance
```

---

# User Input

A user provides a fitness-related goal.

Examples:

```text
I want to lose 10 kg

Create a hypertrophy plan

Help me prepare for a marathon

Design a nutrition strategy for fat loss

Research whether creatine is effective

Build a beginner strength program

Calculate my macros
```

---

# Expected User Outcome

The final output should not be:

```text
A short answer

A generic tip

A motivational response
```

The final output should be:

```text
A complete plan

A practical strategy

Actionable recommendations

Supporting evidence

Confidence indicators
```

---

# Primary User Journey

## Step 1 — User Submits Goal

Example:

```text
I want to lose weight.
```

---

## Step 2 — Goal Classification

The system identifies:

```text
Goal Type

Fat Loss
Muscle Gain
Strength
Endurance
Nutrition
Supplement Research
General Fitness
```

---

## Step 3 — Information Completeness Check

The system evaluates whether enough information exists to create a safe recommendation.

Typical required information may include:

```text
Age

Sex

Height

Weight

Activity Level

Training Experience

Goal

Timeline
```

---

### If Information Is Missing

The agent requests clarification.

Example:

```text
To create a suitable fat-loss plan, I need:

- Age
- Sex
- Height
- Weight
- Activity level
- Target weight
```

The workflow pauses until the user responds.

---

### If Information Is Complete

The agent proceeds directly to:

```text
Research

Planning

Verification

Plan Generation
```

---

# Happy Path #1

## Fat Loss Goal With Missing Information

User:

```text
I want to lose weight.
```

Agent:

```text
Please provide:

- Age
- Sex
- Height
- Current weight
- Activity level
- Target weight
```

User:

```text
Male
30 years old
175 cm
85 kg

Gym 3x/week

Goal: 75 kg
```

Agent performs:

```text
Research

Planning

Verification

Plan Generation
```

Final Output:

### Executive Summary

```text
Current Weight: 85 kg

Target Weight: 75 kg

Estimated Timeline:
4–6 months

Recommended Rate:
0.4–0.6 kg/week
```

### Nutrition Strategy

```text
Calories

Protein

Carbohydrates

Fat
```

### Training Strategy

```text
Resistance Training

Cardio

Daily Activity Targets
```

### Risks & Considerations

```text
Potential adherence risks

Recovery concerns

Recommended monitoring
```

### Supporting Evidence

```text
Research findings

Scientific references

Guideline-based recommendations
```

### Confidence

```text
Verification Status

Evidence Coverage

Confidence Level
```

---

# Happy Path #2

## Complete Information Provided Up Front

User:

```text
30-year-old male

175 cm

85 kg

Gym 3x/week

Goal: 75 kg within 5 months

Create a fat-loss plan.
```

The system immediately proceeds to:

```text
Research

Planning

Verification

Output Generation
```

No clarification round is required.

---

# Happy Path #3

## Supplement Research

User:

```text
Research whether creatine improves muscle growth.
```

Agent performs:

```text
Literature Review

Evidence Collection

Evidence Verification

Conclusion Generation
```

Final Output:

```text
Evidence Summary

Benefits

Limitations

Practical Recommendations

Confidence Rating
```

---

# Edge Case #1

## Goal Is Too Ambiguous

User:

```text
I want to get fit.
```

Agent:

```text
Getting fit can mean several things:

- Fat loss
- Muscle gain
- Strength improvement
- Endurance improvement

Which outcome is your primary goal?
```

Workflow pauses until clarification is provided.

---

# Edge Case #2

## Conflicting Goal Information

User:

```text
Current Weight: 65 kg

Target Weight: 70 kg

Goal: Lose Weight
```

Agent:

```text
Your target weight is higher than your current weight.

Would you like to:

1. Gain weight to 70 kg
2. Adjust your target weight
```

Workflow pauses until clarification.

---

# Edge Case #3

## Unrealistic Fat Loss Goal

User:

```text
Current Weight: 90 kg

Goal Weight: 70 kg

Timeline: 1 Month
```

Agent:

```text
This target would require an unsafe rate of weight loss.

A more realistic timeline would be significantly longer.

Would you like:

- A safer recommendation
- A feasibility analysis
```

Workflow pauses.

---

# Edge Case #4

## Critical Information Missing

User:

```text
Calculate my macros.
```

Agent:

```text
I need:

- Age
- Sex
- Height
- Weight
- Activity level
- Goal

before calculating accurate macro targets.
```

No plan generation occurs.

---

# Edge Case #5

## User Leaves Mid-Workflow

User:

```text
I want to lose weight.
```

Agent requests required information.

User leaves.

System State:

```text
Waiting for User Input
```

Later:

```text
Continue.
```

Agent resumes from the clarification stage.

No collected information is lost.

---

# Edge Case #6

## Weak Evidence For Fitness Claim

User:

```text
Does this new viral diet guarantee fat loss?
```

Agent performs research.

Final Response:

```text
Current evidence is insufficient to support a reliable conclusion.

Evidence Quality:
Low

Confidence:
Low

Recommendation:
Use caution until stronger evidence becomes available.
```

---

# Edge Case #7

## Unsafe Training Recommendation Request

User:

```text
Create a workout plan with 4 hours of training every day.
```

Agent:

```text
This workload may exceed recovery capacity for most individuals.

A safer recommendation would include:

- Appropriate training volume
- Recovery days
- Progressive overload strategy
```

---

# Edge Case #8

## Medical Condition Beyond Scope

User:

```text
I have chest pain during exercise.

Create a training plan.
```

Agent:

```text
This may require medical evaluation before exercise planning.

Please consult a qualified healthcare professional.

PT AI cannot diagnose or assess medical conditions.
```

No training plan is generated.

---

# Edge Case #9

## Non-Fitness Request

User:

```text
Help me write a business plan.
```

Agent:

```text
PT AI only supports fitness-related goals.

Examples include:

- Fat loss
- Muscle gain
- Nutrition
- Strength training
- Endurance training
- Supplement research
```

No research workflow is started.

---

# Approval Flow

Before finalizing any generated plan, the user receives a review opportunity.

Example:

```text
Your plan is ready.

Would you like to approve and finalize this plan?
```

## Approve

```text
Approve
```

Outcome:

```text
Plan finalized.
```

## Request Revision

```text
I want a faster rate of fat loss.
```

Outcome:

```text
Plan returns to planning and verification.

A revised version is generated.
```

---

# User Experience State Machine

```text
Fitness Goal
      ↓

Fitness Domain?

 ├─ No
 │
 └─ Reject & Redirect
      ↓

 └─ Yes
      ↓

Information Complete?

 ├─ No
 │
 └─ Clarification Request
      ↓
   User Response
      ↓

 └─ Yes
      ↓

Research
      ↓

Planning
      ↓

Verification
      ↓

Needs Revision?

 ├─ Yes
 │
 └─ Revise
      ↓

 └─ No
      ↓

Draft Ready
      ↓

User Review
      ↓

Approval
      ↓

Final Plan
```

---

# Success Criteria

A successful experience means:

* The request is fitness-related.
* Missing information is explicitly requested.
* Ambiguous goals are clarified.
* Unsafe goals are challenged.
* Recommendations are evidence-backed.
* Plans are actionable.
* Uncertainty is communicated honestly.
* Outputs are verified before delivery.
* Users can request revisions before finalization.

---