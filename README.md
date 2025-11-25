# AI-Assisted Web Browser (POC)

## Overview

**AI-Assisted Web Browser (POC)** is a proof-of-concept exploring how autonomous AI agents can reliably operate a real browser using natural language instructions. The project emerged from a practical challenge: existing AI browser-automation tools such as WebVoyager and others were promising but often struggled in real usage—either missing elements, failing on dynamic UI updates, or losing track of state.

This POC takes a different approach. It combines:
 * LLM-based intent understanding
 * Agentic planning and error handling
 * A grounded hybrid perception layer using both:
   * visual context
   * curated DOM data limited to visible, actionable elements

Together, this enables agents to execute multi-step web tasks—reading the page, planning the next step, interacting with elements, recovering from failures, and completing workflows with higher reliability than naive LLM-driven automation.

## Solution Summary

The POC implements a **two-agent architecture** that connects LLM-based reasoning with deterministic browser automation using Playwright. The system treats each web task as a guided loop: interpret intent → observe browser → decide next action → execute → repeat until completion.

At a high level:

* A **Coordinator Agent** interprets the user’s natural-language request and breaks it into actionable goals.
* For each goal, it launches a **Web Automation Agent** that operates inside a real browser session.
* The Web Automation Agent proceeds step-by-step by grounding every decision in **visible DOM elements** and a **live page screenshot**, ensuring predictable actions rather than hallucinated guesses.
* Results or required user input flow back to the Coordinator Agent, which may refine the plan or proceed to the next goal.

This creates a controlled, iterative loop where the LLM reasons *about what to do*, and the automation layer handles *how to do it safely*.

## Agents

### 1. Coordinator Agent

The Coordinator is the system’s high-level decision-maker. It handles the user request, forms a plan, and delegates browser execution to a Web Automation Agent.

#### Responsibilities

* Interpret user intent and classify whether it requires browser interaction
* Break down complex tasks into smaller goals
* Dispatch each goal to a Web Automation Agent
* Merge intermediate results into a final response
* Ask the user for clarification whenever required

#### Internal Nodes

* **call_model** — query the LLM for intent and task planning
* **process_model_output** — extract goals, classification, and next steps
* **handle_tool_call** — create and manage Web Automation Agent executions
* **process_post_tool_calls** — synthesize output and communicate it back to user


### 2. Web Automation Agent

The Web Automation Agent is responsible for safely operating the browser. It works in a perception–action loop until it achieves the assigned goal or determines it cannot proceed.

#### Responsibilities

* Capture the browser’s current state (DOM snapshot + screenshot)
* Ask the model: **“Given this state, what should I do next?”**
* Perform deterministic actions via Playwright (click, type, navigate, etc.)
* Detect task completion or report back if user input is needed
* Return structured updates to the Coordinator Agent

#### Internal Nodes

* **take_snapshot** — extract visible DOM elements and a screenshot
* **call_model** — request the model's next action recommendation
* **execute_action** — perform the browser action (clicks, text input, navigation)
  * Includes terminating the loop if the goal is complete
  * Or returning control to the Coordinator if user input is required

---
![Flow Diagram](https://raw.githubusercontent.com/divyanshu-arora-92/yb-browser/main/flow_diagram.png)
