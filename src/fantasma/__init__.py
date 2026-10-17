"""
Il Fantasma — v0.02-dev framework
Strato di ragionamento interno: emerge, agisce, scompare.

Decisioni dr. Bulla: 5.1 stessa AI interpreta, 5.2 cache offuscata -> crypto-shredding,
5.3 amnesia dopo output, 5.4 amnesia a distruzione di chiave. LLM: DeepSeek-V4.1-Flash.
"""

from .gate import HeuristicGate, GateDecision
from .codec import PrivateNumericCodec, GhostThought, INTERPRET_MARKER
from .memory import EphemeralMemory, ObfuscatedCache, obfuscate_numeric, deobfuscate_numeric
from .audit import AuditLogger, AuditEvent
from .pipeline import FantasmaPipeline, FantasmaResult, default_mock_llm
from .llm_deepseek import make_deepseek_llm, get_config, ping as deepseek_ping

from .secret import SecretBytes, OneTimeKey, SecretRegion
from .secret import validate_canonical_19, digest_to_canonical_19, random_canonical_19, CODE_DIGITS
from .crypto import CryptoShredder, SealedBlob, seal_with_key, open_with_key, scrypt_commitment, TimedCommitment, entropy_bits, enumerate_years, CODE_DIGITS_CANONICAL, CODE_DIGITS_LEGACY, SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_MS_PER_GUESS_CORE
from .hygiene import apply_process_hygiene, lock_buffer, unlock_buffer, lock_secret_region, unlock_secret_region
from .hygiene import secure_wipe_buffer
from .forensics import generate_runtime_canary, count_needle_in_stores, count_variants_in_stores, count_unexpected, count_variants_unexpected, needle_variants, scan_process_mem, scan_filesystem, compute_R, evaluate_claim, assert_scanner_sane
from .ghost_window import ghost_window, assert_no_fork_in_window, scrub_frame_locals, release_traceback, scrub_traceback, install_scrubbing_excepthook, recommended_start_method
from .reform_guard import ReformulationGuard, LeakageDetectedError, canonical_numbers_in, build_call1_prompt, CALL1_RIGID_TAIL
from .pii_cover import CoverMapping, CoverResult, cover_text, cover_open_classes_with_local_model, find_cover_spans
from .pii_cover import cf_ok, piva_ok, iban_ok, luhn_ok
from .bolt import BoltRegistry, BoltReceipt, BoltState, UseAfterDestroyError
from .arms import run_arm_reformonly_v04, run_arm_clear_v04, run_arm_random_v04, derived_code
from .pipeline_v02 import FantasmaPipelineV02, FantasmaResultV02, default_mock_llm_v02
from .llm_ollama import make_ollama_llm, DEFAULT_MODEL as OLLAMA_DEFAULT_MODEL
from .bench_gsm8k_v03 import run_benchmark_v03, mcnemar, bootstrap_diff

__all__ = [
    "HeuristicGate",
    "GateDecision",
    "PrivateNumericCodec",
    "GhostThought",
    "INTERPRET_MARKER",
    "EphemeralMemory",
    "ObfuscatedCache",
    "obfuscate_numeric",
    "deobfuscate_numeric",
    "AuditLogger",
    "AuditEvent",
    "FantasmaPipeline",
    "FantasmaResult",
    "default_mock_llm",
    "make_deepseek_llm",
    "get_config",
    "deepseek_ping",
    "SecretBytes",
    "OneTimeKey",
    "SecretRegion",
    "CryptoShredder",
    "SealedBlob",
    "seal_with_key",
    "open_with_key",
    "scrypt_commitment",
    "TimedCommitment",
    "entropy_bits",
    "enumerate_years",
    "CODE_DIGITS_CANONICAL",
    "CODE_DIGITS_LEGACY",
    "apply_process_hygiene",
    "lock_buffer",
    "unlock_buffer",
    "lock_secret_region",
    "unlock_secret_region",
    "generate_runtime_canary",
    "count_needle_in_stores",
    "count_variants_in_stores",
    "count_unexpected",
    "count_variants_unexpected",
    "needle_variants",
    "scan_process_mem",
    "scan_filesystem",
    "compute_R",
    "evaluate_claim",
    "assert_scanner_sane",
    "ghost_window",
    "assert_no_fork_in_window",
    "scrub_frame_locals",
    "release_traceback",
    "scrub_traceback",
    "install_scrubbing_excepthook",
    "recommended_start_method",
    "secure_wipe_buffer",
    "ReformulationGuard",
    "LeakageDetectedError",
    "canonical_numbers_in",
    "build_call1_prompt",
    "CoverMapping",
    "CoverResult",
    "cover_text",
    "cover_open_classes_with_local_model",
    "find_cover_spans",
    "cf_ok",
    "piva_ok",
    "iban_ok",
    "luhn_ok",
    "run_arm_reformonly_v04",
    "run_arm_clear_v04",
    "run_arm_random_v04",
    "derived_code",
    "validate_canonical_19",
    "digest_to_canonical_19",
    "random_canonical_19",
    "BoltRegistry",
    "BoltReceipt",
    "BoltState",
    "UseAfterDestroyError",
    "FantasmaPipelineV02",
    "FantasmaResultV02",
    "default_mock_llm_v02",
    "make_ollama_llm",
    "OLLAMA_DEFAULT_MODEL",
    "run_benchmark_v03",
    "mcnemar",
    "bootstrap_diff",
]

__version__ = "0.5.0-dev"
