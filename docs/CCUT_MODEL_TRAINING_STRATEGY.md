# CCUT Model Training Strategy

## 1. Strategy Overview
CCUT does not aim to train foundation models from scratch. Instead, it uses high-performance models (e.g., Qwen) as **Teachers** or **Staff** to train and refine **CCUT-Owned Specialist Models**.

## 2. CCUT Specialist Models
The following internal models are long-term assets of CCUT:
- **StoryIntent Classifier**: Mapping user input to narrative structures.
- **Proposal Ranker**: Scoring the quality and relevance of edit proposals.
- **Cut Quality Judge**: Identifying optimal transition points.
- **User Preference Model**: Learning individual user styles.
- **Fragment Value Scorer**: Assessing the semantic importance of video segments.

## 3. Training Architecture
- **Base Model + Adapter**: Foundation models (e.g., Qwen-7B) are used as a base, with CCUT knowledge stored in **LoRA** or **Adapters**.
- **Teacher-Student Flow**: Qwen acts as the teacher model to generate training data or labels for smaller, specialist student models.

## 4. Data Accumulation
Training data is harvested from standard system events:
- `user_message`: Direct user input.
- `story_plan snapshot`: The state of the narrative plan at decision time.
- `story_intent_patch`: The generated adjustment instructions.
- `user correction`: Explicit changes made by the user.
- `proposal selected/rejected`: Reinforcement signals from proposal choice.
- `final export / render QA`: Success/failure signals from the final output.
- `feedback/rating`: Direct qualitative signals.

## 5. Privacy and Security
All training data must be handled with strict attention to user privacy. Data should be anonymized, and external transmission is prohibited for sensitive assets.

## 6. Implementation Roadmap
LoRA and SFT (Supervised Fine-Tuning) are reserved for future stages and are not part of the current phase.
