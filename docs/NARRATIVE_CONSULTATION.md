# Narrative Consultation

## 1. Definition

Narrative Consultation is the pre-proposal dialogue phase of CCUT.

CCUT does not immediately present A/B edit proposals after analysis.  
Instead, it first interprets the analyzed video data as a possible story, presents a narrative draft to the user, asks for feedback, and converts the user’s natural-language response into StoryIntent.

## 2. Core Flow

```text
Upload
→ Analysis
→ Semantic Fragment
→ Narrative Draft
→ User Consultation
→ StoryIntent
→ A/B Proposal
→ Preview / Commit
→ Export
```

## 3. Purpose

Narrative Consultation exists to prevent CCUT from behaving like a black-box auto editor.

It allows the user to:

* understand how CCUT interpreted the footage
* correct the story direction before editing
* express intent in natural language
* preserve final decision authority

## 4. What CCUT Shows

During this phase, CCUT shows:

* narrative draft
* source interpretation
* possible story flow
* quality/risk notes
* natural language prompt for feedback

CCUT does not show:

* A/B edit videos
* final proposal cards
* export button as a main action
* forced form choices

## 5. Conversation Principle

The interaction should feel like talking to an AI editor.

CCUT should not invent a new chat grammar.
The UI should follow familiar ChatGPT-style conversation patterns.

## 6. User Input Examples

* “사람 중심으로 해줘.”
* “풍경은 줄이고 빠르게.”
* “아이 장면을 꼭 살려.”
* “여러 영상 골고루 써줘.”
* “좋아, 이대로 제안해줘.”

## 7. Output

The output of Narrative Consultation is StoryIntent.

StoryIntent is then passed to the proposal generation stage.
