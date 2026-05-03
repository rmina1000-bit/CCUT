# ChatGPT Form Chat UX

## 1. Principle

CCUT should not invent a new chat grammar.

Users are already familiar with ChatGPT-style conversation.  
CCUT should adopt that familiar interaction pattern for Narrative Consultation.

## 2. Goal

The user should feel:
“I am talking to an AI editor.”

The user should not feel:
“I am filling out a strange editing form.”

## 3. Required UX

- messages accumulate vertically
- assistant messages are calm and readable
- user messages are not overly colored
- line breaks are natural
- previous messages remain visible
- input box is the primary interaction
- suggestion chips are secondary
- no report/PPT/card feeling

## 4. Visual Direction

Preferred:
- white/gray-centered text
- soft contrast
- low visual noise
- comfortable paragraph width
- natural spacing

Avoid:
- strong blue user bubbles
- large framed cards
- heavy borders
- mandatory-looking buttons
- replacing previous conversation content

## 5. Quick Reply Chips

Quick replies may exist, but only as optional suggestions.

Examples:
- 이대로 제안해줘
- 사람 중심으로
- 풍경 줄여
- 더 빠르게
- 여러 영상 골고루

Clicking a chip must append a user message to the chat history.

## 6. Chat Input

The input field should invite natural language.

Recommended placeholder:
“편하게 말씀해 주세요. 예: 사람 중심으로 / 더 빠르게 / 풍경 줄여”

## 7. Acceptance Criteria

PASS if:
- it feels like a familiar AI chat
- user can type naturally
- chat history is preserved
- A/B only appears after confirmation
- no new network or console errors

FAIL if:
- it feels like a form
- messages are replaced
- user message color is visually distracting
- conversation feels like two monologues
