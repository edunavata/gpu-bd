"""GPU Listing Normalization
===========================

Deterministic lexical normalization for Bronze GPU listings.

This module extracts stable textual hints from a single Bronze record without
guessing or fuzzy matching. It never touches external state and is safe to use
in unit tests or deterministic pipelines.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Literal, Mapping, Optional


VendorHint = Literal["NVIDIA", "AMD", "INTEL"]


# Using a frozen dataclass keeps the return object explicit and immutable while
# still providing strong typing for downstream deterministic matching.
@dataclass(frozen=True, slots=True)
class NormalizedCandidate:
    """Normalized hints extracted from a Bronze GPU listing.

    :ivar vendor_hint: Vendor hint derived from name tokens.
    :ivar series_hint: Brand series hint (e.g., ``GeForce RTX 50``).
    :ivar model_name_hint: Model name hint (e.g., ``RTX 5070 Ti``).
    :ivar aib_manufacturer_hint: AIB manufacturer hint (e.g., ``GIGABYTE``).
    :ivar model_suffix_hint: Model suffix hint (e.g., ``AORUS ELITE``).
    :ivar vram_gb_hint: Parsed VRAM capacity in GB.
    :ivar memory_type_hint: Memory type hint (``GDDR6``, ``GDDR6X``, ``GDDR7``).
    :ivar hdmi_count_hint: HDMI port count when explicitly stated.
    :ivar displayport_count_hint: DisplayPort count when explicitly stated.
    """

    vendor_hint: Optional[VendorHint] = None
    series_hint: Optional[str] = None
    model_name_hint: Optional[str] = None
    aib_manufacturer_hint: Optional[str] = None
    model_suffix_hint: Optional[str] = None
    vram_gb_hint: Optional[int] = None
    memory_type_hint: Optional[str] = None
    hdmi_count_hint: Optional[int] = None
    displayport_count_hint: Optional[int] = None


@dataclass(frozen=True, slots=True)
class _ManufacturerMatch:
    canonical: str
    tokens: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ModelHints:
    vendor: Optional[VendorHint]
    series_hint: Optional[str]
    model_name_hint: Optional[str]
    model_number: Optional[str]
    model_tokens: frozenset[str]


_CLEAN_RE = re.compile(r"[^A-Z0-9\-\+]+")
_WS_RE = re.compile(r"\s+")
_VRAM_GB_RE = re.compile(r"\b(\d{1,3})\s*GB\b")
_VRAM_G_RE = re.compile(r"\b(\d{1,3})G\b")
_MEMORY_TYPE_RE = re.compile(r"\b(GDDR6X|GDDR7|GDDR6)\b")
_HDMI_COUNT_RE = re.compile(r"\b(\d+)\s*X\s*HDMI\b")
_DP_COUNT_RE = re.compile(r"\b(\d+)\s*X\s*(DP|DISPLAYPORT|DISPLAY\s*PORT)\b")

_NVIDIA_MODEL_RE = re.compile(
    r"\bRTX[\s\-]*([0-9]{3,4})(?:[\s\-]*(TI))?(?:[\s\-]*(SUPER))?\b"
)
_AMD_MODEL_RE = re.compile(r"\bRX[\s\-]*([0-9]{3,4})(?:[\s\-]*(XTX|XT|GRE))?\b")
_INTEL_MODEL_RE = re.compile(r"\bARC[\s\-]*([A-Z])[\s\-]*([0-9]{3,4})\b")

_VENDOR_PATTERNS: tuple[tuple[VendorHint, re.Pattern[str]], ...] = (
    ("NVIDIA", re.compile(r"\b(NVIDIA|GEFORCE|RTX)\b")),
    ("AMD", re.compile(r"\b(AMD|RADEON|RX)\b")),
    ("INTEL", re.compile(r"\b(INTEL|ARC)\b")),
)

_VENDOR_TOKENS = {"NVIDIA", "GEFORCE", "AMD", "RADEON", "INTEL", "ARC"}
_MEMORY_TOKENS = {"GDDR6", "GDDR6X", "GDDR7"}
_PORT_TOKENS = {"HDMI", "DP", "DISPLAYPORT", "DISPLAY", "PORT"}
_NUMERIC_TOKEN_RE = re.compile(r"^\d+$")
_VRAM_TOKEN_RE = re.compile(r"^\d{1,3}G(B)?$")

_AIB_MANUFACTURER_ALIASES: dict[str, tuple[str, ...]] = {
    "ASUS": ("ASUS",),
    "GIGABYTE": ("GIGABYTE",),
    "MSI": ("MSI",),
    "SAPPHIRE": ("SAPPHIRE",),
    "POWERCOLOR": ("POWERCOLOR", "POWER COLOR"),
    "ASROCK": ("ASROCK", "AS ROCK"),
    "XFX": ("XFX",),
    "ACER": ("ACER",),
    "GAINWARD": ("GAINWARD",),
    "PALIT": ("PALIT",),
    "ZOTAC": ("ZOTAC",),
    "NVIDIA": ("NVIDIA",),
    "INTEL": ("INTEL",),
}

_MODEL_TOKEN_RE = re.compile(r"\b(nvidia|amd|geforce|radeon|rtx|rx)\b")


def _compile_alias_pattern(alias: str) -> re.Pattern[str]:
    """Compile a word-boundary regex for a multi-token alias.

    :param alias: Alias string in uppercase.
    :type alias: str
    :returns: Compiled regex pattern for the alias.
    :rtype: re.Pattern[str]
    """

    tokens = alias.split()
    if not tokens:
        return re.compile(r"^$")
    pattern = r"\b" + r"\s+".join(re.escape(token) for token in tokens) + r"\b"
    return re.compile(pattern)


_AIB_PATTERNS: tuple[tuple[str, tuple[str, ...], re.Pattern[str]], ...] = tuple(
    (canonical, tuple(alias.split()), _compile_alias_pattern(alias))
    for canonical, aliases in _AIB_MANUFACTURER_ALIASES.items()
    for alias in aliases
)


def _clean_text(text: str) -> str:
    """Normalize casing and separators for deterministic parsing.

    :param text: Raw listing text.
    :type text: str
    :returns: Uppercased, ASCII-friendly, whitespace-collapsed text.
    :rtype: str
    """

    upper = text.upper()
    cleaned = _CLEAN_RE.sub(" ", upper)
    return _WS_RE.sub(" ", cleaned).strip()


def canonical_model_key(value: Optional[str]) -> str:
    """Normalize a GPU model string into a canonical key."""

    if not value:
        return ""
    text = value.lower()
    text = _MODEL_TOKEN_RE.sub(" ", text)
    text = re.sub(r"(?<=\d)(?=[a-z])|(?<=[a-z])(?=\d)", " ", text)
    text = _WS_RE.sub(" ", text)
    return text.strip()


def _extract_vram_gb(text: str) -> Optional[int]:
    """Extract VRAM capacity in GB from text.

    :param text: Normalized listing text.
    :type text: str
    :returns: VRAM capacity in GB when explicitly present, else ``None``.
    :rtype: int | None
    """

    match = _VRAM_GB_RE.search(text)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _extract_memory_type(text: str) -> Optional[str]:
    """Extract memory type token from text.

    :param text: Normalized listing text.
    :type text: str
    :returns: Memory type token if present, else ``None``.
    :rtype: str | None
    """

    match = _MEMORY_TYPE_RE.search(text)
    if not match:
        return None
    return match.group(1).upper()


def _extract_port_count(text: str, pattern: re.Pattern[str]) -> Optional[int]:
    """Extract a summed connector count from text.

    :param text: Normalized listing text.
    :type text: str
    :param pattern: Compiled regex pattern for connector counts.
    :type pattern: re.Pattern[str]
    :returns: Summed count when explicit counts are present, else ``None``.
    :rtype: int | None
    """

    total = 0
    found = False
    for match in pattern.finditer(text):
        found = True
        try:
            total += int(match.group(1))
        except ValueError:
            continue
    if not found:
        return None
    return total or None


def _parse_model(text: str) -> _ModelHints:
    """Parse vendor and model hints from normalized text.

    :param text: Normalized listing text.
    :type text: str
    :returns: Parsed model hints and token set for suffix exclusion.
    :rtype: _ModelHints
    """

    match = _NVIDIA_MODEL_RE.search(text)
    if match:
        number = match.group(1)
        ti_token = match.group(2)
        super_token = match.group(3)
        tokens = {"RTX", number}
        model_name = f"RTX {number}"
        if ti_token:
            tokens.add("TI")
            model_name += " Ti"
        if super_token:
            tokens.add("SUPER")
            model_name += " SUPER"
        series_hint = None
        if len(number) >= 4:
            series_hint = f"GeForce RTX {number[:2]}"
        return _ModelHints(
            vendor="NVIDIA",
            series_hint=series_hint,
            model_name_hint=model_name,
            model_number=number,
            model_tokens=frozenset(tokens),
        )

    match = _AMD_MODEL_RE.search(text)
    if match:
        number = match.group(1)
        suffix = match.group(2)
        tokens = {"RX", number}
        model_name = f"RX {number}"
        if suffix:
            tokens.add(suffix)
            model_name += f" {suffix}"
        series_hint = None
        if len(number) >= 4:
            series_hint = f"Radeon RX {number[0]}000"
        return _ModelHints(
            vendor="AMD",
            series_hint=series_hint,
            model_name_hint=model_name,
            model_number=number,
            model_tokens=frozenset(tokens),
        )

    match = _INTEL_MODEL_RE.search(text)
    if match:
        letter = match.group(1)
        number = match.group(2)
        model_code = f"{letter}{number}"
        tokens = {"ARC", model_code}
        return _ModelHints(
            vendor="INTEL",
            series_hint=None,
            model_name_hint=f"ARC {model_code}",
            model_number=number,
            model_tokens=frozenset(tokens),
        )

    return _ModelHints(
        vendor=None,
        series_hint=None,
        model_name_hint=None,
        model_number=None,
        model_tokens=frozenset(),
    )


def _infer_vendor(text: str) -> Optional[VendorHint]:
    """Infer vendor from general tokens when no model match is found.

    :param text: Normalized listing text.
    :type text: str
    :returns: Vendor hint if present, else ``None``.
    :rtype: str | None
    """

    best_vendor: Optional[VendorHint] = None
    best_index: Optional[int] = None
    for vendor, pattern in _VENDOR_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        idx = match.start()
        if best_index is None or idx < best_index:
            best_vendor = vendor
            best_index = idx
    return best_vendor


def _extract_aib_manufacturer(text: str) -> Optional[_ManufacturerMatch]:
    """Extract the earliest AIB manufacturer token from text.

    :param text: Normalized listing text (typically the name head).
    :type text: str
    :returns: Matched manufacturer info or ``None``.
    :rtype: _ManufacturerMatch | None
    """

    best_match: Optional[_ManufacturerMatch] = None
    best_index: Optional[int] = None
    for canonical, tokens, pattern in _AIB_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        idx = match.start()
        if best_index is None or idx < best_index:
            best_match = _ManufacturerMatch(canonical=canonical, tokens=tuple(tokens))
            best_index = idx
    return best_match


def _extract_model_suffix(
    text: str, manufacturer: Optional[_ManufacturerMatch], model_hints: _ModelHints
) -> Optional[str]:
    """Extract model suffix tokens from the name head.

    :param text: Normalized listing head text (pre-comma segment).
    :type text: str
    :param manufacturer: Matched AIB manufacturer, if any.
    :type manufacturer: _ManufacturerMatch | None
    :param model_hints: Parsed model hints for exclusion.
    :type model_hints: _ModelHints
    :returns: Normalized model suffix or ``None``.
    :rtype: str | None
    """

    tokens = text.split()
    if not tokens:
        return None

    remove_tokens = set(_VENDOR_TOKENS)
    remove_tokens.update(model_hints.model_tokens)
    if manufacturer:
        remove_tokens.update(manufacturer.tokens)

    filtered: list[str] = []
    model_number = model_hints.model_number or ""
    for token in tokens:
        if token in remove_tokens:
            continue
        if token in _MEMORY_TOKENS:
            continue
        if token in _PORT_TOKENS:
            continue
        if _NUMERIC_TOKEN_RE.match(token):
            continue
        if _VRAM_TOKEN_RE.match(token):
            continue
        if model_number and model_number in token:
            continue
        if _VRAM_G_RE.match(token):
            continue
        filtered.append(token)

    if not filtered:
        return None
    return " ".join(filtered)


def normalize(bronze_record: Mapping[str, Any]) -> NormalizedCandidate:
    """Normalize a Bronze GPU listing into lexical hints.

    :param bronze_record: Raw Bronze listing dictionary.
    :type bronze_record: Mapping[str, Any]
    :returns: Normalized hints for downstream matching.
    :rtype: NormalizedCandidate
    """

    try:
        raw_name = bronze_record.get("product_name_raw")
        if not isinstance(raw_name, str) or not raw_name.strip():
            return NormalizedCandidate()

        name_clean = _clean_text(raw_name)
        head_raw = raw_name.split(",", 1)[0]
        head_clean = _clean_text(head_raw)

        model_hints = _parse_model(name_clean)
        vendor_hint = model_hints.vendor or _infer_vendor(name_clean)

        manufacturer = _extract_aib_manufacturer(head_clean)

        model_suffix = None
        if model_hints.model_name_hint:
            model_suffix = _extract_model_suffix(head_clean, manufacturer, model_hints)

        vram_gb = _extract_vram_gb(name_clean)
        memory_type = _extract_memory_type(name_clean)
        hdmi_count = _extract_port_count(name_clean, _HDMI_COUNT_RE)
        displayport_count = _extract_port_count(name_clean, _DP_COUNT_RE)

        return NormalizedCandidate(
            vendor_hint=vendor_hint,
            series_hint=model_hints.series_hint,
            model_name_hint=model_hints.model_name_hint,
            aib_manufacturer_hint=manufacturer.canonical if manufacturer else None,
            model_suffix_hint=model_suffix,
            vram_gb_hint=vram_gb,
            memory_type_hint=memory_type,
            hdmi_count_hint=hdmi_count,
            displayport_count_hint=displayport_count,
        )
    except Exception:
        return NormalizedCandidate()


def _demo() -> None:
    """Run a minimal normalization demo for manual inspection.

    :returns: ``None``.
    :rtype: None
    """

    samples = [
        {
            "product_name_raw": (
                "INNO3D GeForce RTX 5080 iCHILL Frostbite Pro, 16GB GDDR7, HDMI, 3x DP"
            )
        },
    ]
    for sample in samples:
        print(normalize(sample))


if __name__ == "__main__":
    _demo()
