# Clarification Engine Deep Dive

Status: In progress

[Confidence Accumulation](Clarification%20Engine%20Deep%20Dive/Confidence%20Accumulation%202de83f23b1658073bc62f2ed72d1cc26.md)

[Deterministic Stop & Research Hand-off](Clarification%20Engine%20Deep%20Dive/Deterministic%20Stop%20&%20Research%20Hand-off%202de83f23b16580128f29c3f939e2e3ac.md)

**Role:** The "Empathy & Definition" Layer

## Core Responsibilities

The Clarification Engine is a **State Machine** driven by an LLM. Its purpose is to convert unstructured user intent into a structured "Seed Object" that the Outline Worker can execute on.

The **Clarification Engine** is for extracting the **Internal Context** (User's Vision/Intent).

Clarification Engine should not demand facts. It should **map the user's knowledge boundaries.**

---

### 🧠 The New Clarification Strategy: "Map the Knowns, Flag the Unknowns"

Instead of forcing an answer, the engine must distinguish between:

1. **Hard Constraints:** Things the user *must* have (e.g., "It has to be mobile-first").
2. **Hypotheses:** Things the user *thinks* are true (e.g., "I think people hate Excel for this").
3. **Blind Spots:** Things the user explicitly admits they don't know.

The goal is to generate a **Research Plan** that specifically targets the *Blind Spots*.

### 🔄 The "I Don't Know" Workflow

**Scenario:**

- **Agent:** "Do you know how people currently solve this problem? Are they using Excel or hiring assistants?"
- **User:** "I'm not sure actually. I just know they complain about it."
- **Old Logic:** "Please try to guess." (Bad UX).
- **New Logic:** "No problem. I've marked **Current Workarounds** as a key gap. I will have the Research Agent scan forums and Reddit to see what people are actually doing."

---

### ✅ Revised "What It Should Do" (The Scout Approach)

1. **Assess "Conviction Level"**
    - **Do:** Ask questions to see how certain the user is.
    - *Agent:* "Are you targeting **nurses specifically**, or is that just a guess?"
    - *Goal:* If it's a guess, the Research Engine must validate if nurses are actually the right target. If it's a hard constraint, the Research Engine focuses *only* on nurses.
2. **Capture "Observation" vs. "Market Data"**
    - **Do:** Instead of asking "What are the competitors?", ask "What sparked this idea? Did you see someone struggling with a specific tool?"
    - *Why:* The user *knows* what they saw (Observation). They *don't know* the full market landscape.
    - *Outcome:* If they say "I saw my mom struggling with Quickbooks," you now have a seed for the Research Engine: **Research Quickbooks pain points.**
3. **Turn "Unknowns" into "Research Tasks"**
    - **Do:** Explicitly tell the user when you are adding a task to the backlog.
    - *Agent:* "Okay, so we aren't sure about the pricing model yet. I’ll add **'Competitor Pricing Analysis'** to the research plan."

---

### ❌ Revised "What It Should NOT Do"

1. **Do NOT Ask "Homework" Questions**
    - Don't ask: "What is the Total Addressable Market (TAM)?"
    - Don't ask: "Who are your top 3 competitors?"
    - Don't ask: "Is this technically feasible?"
    - *Correction:* These are the **answers your product provides**, not questions it asks.
2. **Do NOT Penalty for Ignorance**
    - If a schema field (like `Current Solution`) is empty, do not block progress.
    - Mark it as `status: "needs_research"` and move on.

---

### 🛠 The Updated Clarification Flow (User Experience)

This is how the conversation feels with the "Knowledge Gap" approach.

> User: "I want to build a platform for freelance videographers to manage client feedback."
> 
> 
> **Agent (Clarifying Persona):** "Got it. Freelance videographers.
> To help me build the right research plan, I need to know your specific focus:
> **Are you focusing on the *file transfer* part (sending huge video files) or the *feedback/commenting* part (timestamped notes)?**"
> 
> **User:** "Definitely the feedback notes. The file transfer part is already solved by WeTransfer."
> 
> **Agent (Detecting Knowledge):** "Understood. Focus is on **Feedback**.
> You mentioned WeTransfer solves the transfer part. **Do you know if there are already tools for the feedback part, or do you think most people just use email/Whatsapp?**"
> 
> **User:** "I honestly don't know. I assume there are some, but I haven't checked."
> 
> **Agent (Handling the Unknown):** "That’s perfectly fine. That is exactly what I will research.
> **I have marked 'Competitor Landscape for Video Feedback' as a high-priority research task.**
> Now, let's talk about the user..."
> 

---

### 📝 The Final "Handoff Object"

When the Clarification Engine is done, it hands this object to the Orchestrator. This is the "Brain" telling the "Hands" what to do.

JSON

`{
  "idea_context": {
    "core_intent": "Video feedback tool for freelancers",
    "hard_constraints": ["Must be web-based", "Must focus on timestamped comments"],
    "user_observations": ["Clients currently send messy Whatsapp lists"]
  },
  "knowledge_gaps": {
    "competitors": "UNKNOWN", // Trigger: Comprehensive Competitor Search
    "pricing_model": "UNKNOWN", // Trigger: Pricing Analysis
    "technical_feasibility": "ASSUMED_EASY" // Trigger: Feasibility Check (Verify assumption)
  },
  "research_directives": [
    "Find existing video feedback tools specifically for freelancers (not enterprises like Frame.io)",
    "Investigate complaints about 'Whatsapp feedback' on Reddit/Twitter",
    "Check API costs for video hosting"
  ]
}`

### 🚀 Summary of the "Clarification Engine" Role

1. **Ask:** "What is your intent?"
2. **Ask:** "What have you observed personally?"
3. **Detect:** What does the user *not* know?
4. **Action:** Turn those unknowns into **Research Directives**.

### ✅ Functional Requirements (What it MUST do)

1. **Schema Validation Loop:** On every turn, compare current conversation history against the `Idea_Schema` (Problem, Persona, Value, Mechanism). Identify `null` or `weak` fields.
2. **Constraint Extraction:** Differentiate between "Hard Constraints" (must-haves) and "Hypotheses" (assumptions).
3. **Gap-Based Questioning:** Generate **exactly one** high-value question per turn targeting the most critical missing field in the schema.
4. **Mirroring:** Briefly summarize the user's previous input to confirm understanding before asking the next question.
5. **Knowledge Boundary Detection:** Identify when a user *doesn't* know an answer and flag it as a "Research Directive" instead of forcing a guess.

### ❌ Negative Constraints (What it must NOT do)

1. **No Hallucinations:** Do not invent competitors, market size, or feasibility data.
2. **No Solutionizing:** Do not suggest features ("You should use AI for this") unless the user explicitly asks.
3. **No "Consultant Speak":** Avoid generic SWOT questions ("What are your strengths?").
4. **No Scope Creep:** If the user introduces a second product idea, force them to prioritize one.
5. **No Infinite Loops:** Strictly adhere to the "Fatigue Limit" (Max 5 turns).

### ✅ WHAT IT SHOULD DO

1. **Enforce the "Problem First" Rule:**
    - If the user starts with "I want to build an app with Blockchain," the engine must Pivot: "Okay, we can use Blockchain. But what problem does the Blockchain solve for the user that a regular database can't?"
2. **Use "Yes, And..." Thinking:**
    - Validate the user's input, then stretch it. "That makes sense for students. **And** have you considered if teachers might also need a view into this?"
3. **Identify the "Anti-Persona":**
    - Ask: "Who is this product definitely NOT for?" (This clarifies scope faster than asking who it *is* for).
4. **Synthesize at the End:**
    - Before handing off to the Research Engine, it must output a summary: "Here is the concept I have captured: A [Solution] for [User] who struggles with [Problem] because [Current Alternative] is too slow. Is this accurate?"

### ❌ WHAT IT SHOULD NOT DO

1. **Do NOT ask generic "SWOT" questions:**
    - Don't ask: "What are the strengths and weaknesses?" (Users don't know yet).
    - Instead ask: "What makes this risky?"
2. **Do NOT let the user be "The Everything App":**
    - If the user says "It's for everyone," the engine must NOT accept that. It must force narrowness: "To start, we need to win one specific niche. Which one is the easiest to sell to?"
3. **Do NOT act like a Consultant (giving answers):**
    - It should not say: "I think you should target nurses."
    - It should say: "Have you considered nurses? They often face this problem." (Keep agency with the user).

---

## 2. The Logic Algorithm (State Machine) may be

The engine does not just "chat." It follows this execution cycle for every user message:

1. **INGEST:** Receive `user_message` + `conversation_history`.
2. **EXTRACT:** LLM parses the message to update the internal `Current_State_JSON`.
3. **EVALUATE:**
    - Calculate `Confidence_Score` (0.0 to 1.0).
    - Check **Stop Conditions** (see Section 3).
4. **DECIDE:**
    - IF `Stop_Condition == True` → Trigger **HANDOFF**.
    - IF `Stop_Condition == False` → Identify top missing field → Generate **NEXT_QUESTION**.
5. **RESPOND:** Stream the response to the user.

---

## 3. Stop Conditions (Termination Logic)

The engine triggers the **HANDOFF** state when **ANY** of the following occur:

1. **The "Searchable Context" Threshold:**
    - `Target_Persona`, `Core_Problem`, and `Proposed_Solution` fields are all filled and non-vague.
    - Confidence Score > 0.8.
2. **The "Knowledge Wall":**
    - User replies with "I don't know" or equivalent for **2 consecutive turns**.
3. **The "Fatigue Limit":**
    - Conversation reaches **5 turns** (configurable).

The Clarification Engine stops when it crosses one of these **three thresholds**.

It does not need to know *everything*. It just needs to know enough to write a good Google Search query.

### 🛑 The 3 Stop Triggers

### 1. The "Searchable Context" Threshold (The Ideal Stop)

The engine stops the moment it has enough specific keywords to generate high-quality research queries.

- **Criteria:** It has successfully captured:
    - **User Persona** (Who?)
    - **Core Problem** (What's wrong?)
    - **Proposed Mechanism** (How does it solve it?)
- **Why stop here?** Because asking more is useless. The engine can now construct queries like: *"Freelance video editor feedback tools comparison"* or *"Pain points of creative agencies using WhatsApp."*

### 2. The "Knowledge Wall" Threshold (The 'I Don't Know' Stop)

The engine stops if the user answers "I don't know" or is vague for **2 consecutive turns**.

- **Scenario:**
    - *Agent:* "Do you know the specific pain point?" -> *User:* "Not really."
    - *Agent:* "Okay. Do you know who the main competitor is?" -> *User:* "No idea."
- **Action:** **EMERGENCY STOP.** Do not keep asking. The user is now feeling stupid.
- **The Pivot:** "That’s actually a great place to start! It means we have a blank slate. I have marked 'Problem Discovery' and 'Competitor Scan' as our top priorities. Let’s start researching."

### 3. The "Fatigue" Limit (The Hard Stop)

The engine stops automatically after **5 turns (interactions)**, no matter what.

- **Why:** After 5 questions, it feels like an interrogation, not a partnership.
- **Logic:** If the user hasn't clarified the idea in 5 turns, further chatting won't help. The system should take what it has, run a broad research scan, and come back with findings to spark the user's brain.

---

### 🚦 The "Confidence Score" Algorithm

Behind the scenes, the Orchestrator maintains a running score (0 to 100%).

- **Start:** 0%
- **"I want to make a video tool":** +20% (Too broad)
- **"For freelancers":** +20% (Target acquired)
- **"To fix the feedback loop":** +20% (Problem acquired)
- **"Unlike WeTransfer, it focuses on timestamped notes":** +25% (Differentiation acquired)
- **Total:** 85% -> **STOP & EXECUTE.**

### 🏁 The "Exit Handoff" UX

When the stop condition is triggered, the Agent **must** transition smoothly. It shouldn't just say "Bye."

**The Handoff Message:**

> "Okay, I think I have a solid starting point.
> 
> 
> **Here is the core concept I've captured:**
> A feedback tool for freelance videographers that replaces 'WhatsApp chaos' with timestamped notes.
> 
> **What I don't know yet (and will research):**
> 
> - Exact competitors in this niche.
> - Current pricing models for similar tools.
> - Technical feasibility of browser-based rendering.
> 
> **I’ve built a Research Plan to answer these. Shall I unleash the agents?**"
> 

This confirms to the user that:

1. You heard them.
2. You know what's missing.
3. You are ready to work.

---

## 4. The LLM System Prompt

*Pass this prompt to the LLM (e.g., GPT-4o or Claude 3.5 Sonnet) on every turn. The Output must be JSON to allow the Orchestrator to control the UI.*

Markdown

`### SYSTEM ROLE
You are the Clarification Engine for an Idea Intelligence Platform.
Your goal is to interview the user to build a structured "Research Seed Object."
You are NOT a creative brainstorming partner. You are a precise requirement gatherer.

### THE SCHEMA (Target State)
1. Project Name & Domain
2. Target Persona (Specific niche, not "everyone")
3. Core Problem (The pain point)
4. Current Workaround (Competitors/Duck-tape solutions)
5. Proposed Solution (The mechanism)
6. Differentiation (Why it wins)

### RULES OF ENGAGEMENT
1. ONE QUESTION ONLY: Ask exactly one strategic question to fill the most critical missing schema field.
2. DETECT UNKNOWNS: If the user says "I don't know", DO NOT pressure them. Mark it as "Needs Research" and move to the next field.
3. MIRRORING: Start your response by validating what you just heard. "Got it, so you are targeting [Persona]..."
4. NO FLUFF: Be concise. No "That's a wonderful idea!" compliments.

### OUTPUT FORMAT (JSON ONLY)
You must output a JSON object. Do not output raw text outside the JSON.
{
  "thought_process": "Analyze what we have vs what is missing.",
  "updated_schema": {
    "target_persona": "...",
    "core_problem": "...",
    ... (fill known fields, leave null if unknown)
  },
  "confidence_score": 0.0 to 1.0,
  "stop_signal": boolean, // True if we have enough info OR hit limits
  "handoff_summary": "String" // Only if stop_signal is true. A summary of the idea.
  "next_message": "String" // The actual text to show the user. (The mirroring + the question).
}`

---

## 5. UX Flow (User Interaction)

This is a refined UX specification based on your "Message + Dynamic Box" concept. This design keeps the interface clean (single pane) while making the AI feel like a capable tool that builds alongside the user.

### The "Living Box" UX Pattern

In this design, every response from the AI Assistant consists of two distinct parts stacked vertically:

1. **The Conversational Bubble (Top):** The human-like voice asking the question.
2. **The "Thinking Box" (Bottom):** A structured, interactive card that shows exactly what the AI has "saved" to its memory or what it plans to do.

---

### 1. Visual Walkthrough

### Phase 1: The Build-Up (Clarification)

*As the user talks, the "Box" acts as a real-time receipt of the conversation.*

- **User:** "I want to build a marketplace for freelance videographers."
- **AI Response:**
    - **Bubble:** "Got it. Videographers. To narrow this down, are you focusing on **wedding/event** videographers or **commercial/corporate** ones?"
    - **The Box (State: Capture):**
        
        > ✅ Captured Concept
        > 
        
        > Domain: Video Production MarketPersona: Freelance VideographersProblem: Pending...
        > 
        
        > [Icon: Pencil] Edit (User can click this to fix "Videographers" if the AI got it wrong)
        > 

### Phase 2: Handling Unknowns (The "Gap" Detection)

*When the user admits they don't know something, the Box visually acknowledges it as a task, not a failure.*

- **User:** "I'm not sure about competitors. Maybe Fiverr?"
- **AI Response:**
    - **Bubble:** "That's fine. Fiverr is a general competitor, but we need to find niche ones. I'll add a deep competitor scan to the research list."
    - **The Box (State: Gap Identified):**
        
        > ⚠️ Knowledge Gap Identified
        > 
        > - **Assumption:** "Fiverr is the main competitor"
        > - **Action Added:** `+ Competitor Analysis (Niche vs General)`

### Phase 3: The Mission Handoff (Completion)

*The final interaction where the Box transforms into the "Launchpad".*

- **User:** "Exactly. And it needs to handle large file transfers."
- **AI Response:**
    - **Bubble:** "Understood. That gives me a complete picture. I've outlined the research plan below. Review it, and we can start."
    - **The Box (State: Mission Control):**
        
        > 🚀 Research Mission Plan
        > 
        > 
        > 1. Market Validation
        > 
        
        > [x] Search: "Freelance video file transfer pain points"[x] Scan: Reddit r/videography
        > 
        
        > 2. Competitor Check
        > 
        
        > [x] Analyze: Frame.io vs WeTransfer vs Your Idea
        > 
        
        > 3. Technical Feasibility
        > 
        
        > [x] Check: AWS S3 Egress costs for video
        > 
        
        > [ Edit Plan ]  [ Start Research ] ⚡
        > 

---

### 2. Why This UX Works

1. **Immediate Validation:** The user sees the "Captured" data instantly. If the AI hallucinates or misunderstands, the user can click `Edit` in the box *before* answering the next question.
2. **No "Wall of Text":** The text bubble stays short (conversational). The heavy information (lists, plans) lives in the Box.
3. **Seamless Transition:** You don't need a separate "Dashboard" page. The "Start Research" button appears naturally at the end of the chat flow.

### 3. Frontend Component Structure

For your engineer, this is how the `Message` component should be constructed:

JavaScript

# 

`// React Component Structure
function AssistantMessage({ text, metadata }) {
  return (
    <div className="flex flex-col gap-2 mb-4">
      
      {/* 1. The Text Bubble */}
      <div className="bg-gray-100 p-4 rounded-lg text-gray-800 max-w-lg">
        {text}
      </div>

      {/* 2. The Dynamic Box (Rendered based on metadata type) */}
      {metadata && (
        <div className="border border-gray-200 rounded-md p-3 ml-2 max-w-md bg-white shadow-sm">
          
          {/* CASE A: Progress Update */}
          {metadata.type === 'progress' && (
            <div className="text-sm">
              <div className="font-semibold text-green-600 mb-1">✓ Updated Context</div>
              {metadata.captured.map(field => (
                <div key={field.key} className="flex justify-between">
                  <span className="text-gray-500">{field.key}:</span>
                  <span className="font-medium">{field.value}</span>
                </div>
              ))}
            </div>
          )}

          {/* CASE B: Mission Control */}
          {metadata.type === 'mission_control' && (
             <ResearchPlanCard plan={metadata.plan} status={metadata.status} />
          )}
          
        </div>
      )}
    </div>
  );
}`

### 4. Database Integration

This maps perfectly to the `meta_data` column we added to your schema in the previous step.

- **When the AI is clarifying:**
    - `ChatMessage.message`: "Who is the user?"
    - `ChatMessage.meta_data`: `{"type": "progress", "captured": [{"key": "Domain", "value": "Video"}]}`
- **When the AI is ready to research:**
    - `ChatMessage.message`: "Ready to launch."
    - `ChatMessage.meta_data`: `{"type": "mission_control", "plan": [...], "status": "pending"}`

This structure gives you the exact UX you described: a clean, linear chat where the "Thinking" is visualized in a structured box right underneath the conversation.

---

## 6. Handoff & Research Plan Validation

This is the transition from **Clarification Engine** → Outline Worker **Engine**.

**Trigger:** When `stop_signal` is `True`.

**Orchestrator Logic:**

1. Stop the chat input.
2. Take the `updated_schema`.
3. Generate a **Research Plan Object** (using a separate specific prompt).
4. Present the **"Mission Confirmation"** Modal to the user.

**The "Mission Confirmation" Modal (UI):**

> "I have a clear picture of your concept. Here is the Research Plan I propose:"
> 
> 
> **1. Competitor Scan:** Search for "Roommate finder apps" and "Facebook Housing Groups".
> **2. Pain Point Analysis:** Scan Reddit r/badroommates for complaints.
> **3. Technical Feasibility:** Check Google Maps API costs.
> 
> [ Button: **Edit Plan** ] [ Button: **Start Research** ]
> 

**Engineer Implementation Note:**
The `Research Plan` is not just text. It is a list of directives that map to your Workers:

JSON

`"research_plan": [
  { "type": "competitor_search", "query": "roommate finder apps USA" },
  { "type": "trend_scan", "source": "reddit", "subreddit": "badroommates" },
  { "type": "tech_audit", "topic": "Google Maps API pricing" }
]`

**Only when the user clicks "Start Research" does the system instantiate the Research Workers.**