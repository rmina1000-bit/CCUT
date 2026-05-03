"""Candidate registry for Narrative LLM Providers.

This module stores metadata for various LLM candidates.
It is a non-runtime skeleton for documentation and future implementation.
"""

from .narrative_llm_provider import NarrativeLLMProviderInfo

# Provider candidates registry
NARRATIVE_PROVIDER_CANDIDATES = {
    "mock_narrative_llm": NarrativeLLMProviderInfo(
        provider_id="mock_narrative_llm",
        provider_name="Mock Narrative Adapter",
        provider_family="mock",
        runtime="python",
        model_id="rule-based-mock",
        license_name="MIT",
        license_review_required=False,
        status="ACTIVE_MOCK"
    ),
    "qwen3_instruct_local": NarrativeLLMProviderInfo(
        provider_id="qwen3_instruct_local",
        provider_name="Qwen3-Instruct 7B",
        provider_family="qwen",
        runtime="llama-server / ollama",
        model_id="qwen3-7b-instruct",
        license_name="Apache-2.0",
        license_review_required=False,
        status="PRIMARY_CANDIDATE"
    ),
    "mistral_local": NarrativeLLMProviderInfo(
        provider_id="mistral_local",
        provider_name="Mistral-7B-v0.3",
        provider_family="mistral",
        runtime="llama-server / ollama",
        model_id="mistral-7b-instruct-v3",
        license_name="Apache-2.0",
        license_review_required=False,
        status="SECONDARY_CANDIDATE"
    ),
    "gemma_local_caution": NarrativeLLMProviderInfo(
        provider_id="gemma_local_caution",
        provider_name="Gemma-2-9B",
        provider_family="gemma",
        runtime="ollama",
        model_id="gemma-2-9b-it",
        license_name="Google Gemma Terms of Use",
        license_review_required=True,
        status="CAUTION_CANDIDATE"
    ),
    "llama_local_caution": NarrativeLLMProviderInfo(
        provider_id="llama_local_caution",
        provider_name="Llama-3.1-8B",
        provider_family="llama",
        runtime="llama-server / ollama",
        model_id="meta-llama-3.1-8b-instruct",
        license_name="Meta Llama 3.1 Community License",
        license_review_required=True,
        status="CAUTION_CANDIDATE"
    ),
    "future_open_model": NarrativeLLMProviderInfo(
        provider_id="future_open_model",
        provider_name="Future Open Model",
        provider_family="unknown",
        runtime="unknown",
        status="FUTURE_CANDIDATE"
    ),
}
