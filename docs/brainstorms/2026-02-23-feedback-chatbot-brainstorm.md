# Feedback Chatbot Widget — Brainstorm

**Date:** 2026-02-23
**Ticket:** #48 — Add a feedback collection chatbot to the bottom right of the page

## What We're Building

A floating AI-powered chat widget in the bottom-right corner of every page. It acts as a general-purpose assistant that knows about DS-PAL, can guide users, answer data science questions, and collect feedback. Messages are saved to the database for later review.

- **LLM Provider:** HuggingFace Inference API (free tier, already configured in the project)
- **UI:** Custom chat widget built natively with the existing stack (HTMX, Jinja2, Pico CSS)
- **Persistence:** New `chat_messages` table in SQLite

## Why This Approach

- **Custom widget over third-party embed** — Full control over design, integrates with the existing theme system (light/dark), stores feedback directly in our DB, no external branding
- **HuggingFace over other providers** — Free, `HUGGINGFACE_TOKEN` already in config, no new signup needed
- **General assistant over feedback-only** — More useful for colleagues evaluating the app; can explain features, help with data science questions, and collect feedback naturally

## Key Decisions

1. **Widget placement:** Fixed bottom-right, collapsible via a toggle button
2. **Chat model:** Use a capable open model via HuggingFace (e.g., Mistral, Llama)
3. **System prompt:** Describes DS-PAL features, encourages feedback, knows about supported datasets and analysis types
4. **Message storage:** All user messages and bot responses saved to `chat_messages` table with session tracking
5. **Design:** Sharp corners (no border-radius), glass effect background, theme-aware — matches existing aesthetic
6. **Z-index:** 99 (below nav at 100, above main content)
7. **Mobile:** Responsive — full-width on small screens

## UI Design

### Collapsed state
- Small chat bubble icon button, fixed to bottom-right corner
- Subtle, low-profile — doesn't distract from the main content

### Expanded state
- **Slide-up drawer** — animates up from the bottom-right when the icon is clicked
- ~350px wide, ~450px tall
- Glass effect background with sharp corners (matches site aesthetic)
- Header bar with title ("PAL") and close button
- Scrollable message area in the middle
- Text input + send button at the bottom

### Message style
- **Card-style messages** — each message in its own bordered card with sharp corners
- Bot messages left-aligned, user messages right-aligned
- Bot cards have a subtle different border or background to distinguish from user cards
- Timestamps optional (keep it clean)

### Interactions
- Click icon → drawer slides up with smooth animation
- Click close / click icon again → drawer slides down
- Submit message → card appears immediately, bot response streams/appears after

## Personality & Feedback Flow

### Name & tone
- **Name:** PAL (from DS-PAL)
- **Tone:** Professional & concise — helpful, straight to the point, no fluff
- **Opening message:** "Hi, I'm PAL. I can help you navigate DS-PAL, answer data science questions, or collect your feedback. Type 'feedback' anytime to share your thoughts."

### System prompt scope
PAL knows about:
- DS-PAL features: dataset search (Kaggle, HuggingFace, UCI, Data.gov), file uploads (CSV, JSON, Excel, Parquet), clustering analysis (K-Means, DBSCAN), anomaly detection, visualizations
- General data science concepts
- How to use the app (search → select dataset → configure analysis → view results)

### Feedback mode
- User types "feedback" (or clicks a "Give Feedback" button in the chat header)
- PAL switches to structured feedback collection, asking:
  1. "What were you trying to do?"
  2. "How was your experience?"
  3. "Any suggestions for improvement?"
- Feedback responses are flagged in the database for easy filtering

## Open Questions

- Which specific HuggingFace model to use? (depends on free tier availability and quality)
- Should there be a rate limit per session to avoid API abuse?
- Should the chat history persist across page navigations (via session storage)?
