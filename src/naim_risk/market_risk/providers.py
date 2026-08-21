"""Offline-first market data providers and governed instrument validation."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import numpy as np
import pandas as pd

ALLOWED_FIELDS = frozenset(
    {
        "open",
        "high",
        "low",
        "close",
        "adjusted_close",
        "volume",
        "return",
    }
)
INSTRUMENT_TYPES = frozenset(
    {"index", "equity", "uploaded_instrument", "uploaded_portfolio_return"}
)
PERIOD_YEARS = {"one_year": 1, "three_years": 3, "five_years": 5}
_INSTRUMENT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:^/ -]{0,79}$")


class MarketDataError(ValueError):
    """Raised when market data cannot be used safely or reproducibly."""


class ExternalProviderUnavailable(RuntimeError):
    """Raised when a configuration-only external adapter is called."""


@dataclass(frozen=True)
class InstrumentSelection:
    """Validated instrument and requested analysis period."""

    instrument: str
    instrument_type: str
    start_date: date
    end_date: date
    period: str = "custom"

    def __post_init__(self) -> None:
        validate_instrument(
            self.instrument,
            self.instrument_type,
            self.start_date,
            self.end_date,
        )
        if self.period not in {*PERIOD_YEARS, "custom"}:
            raise MarketDataError(f"Unsupported period: {self.period}")

    @classmethod
    def trailing_period(
        cls,
        *,
        instrument: str,
        instrument_type: str,
        end_date: date,
        period: str,
    ) -> InstrumentSelection:
        if period not in PERIOD_YEARS:
            raise MarketDataError("Trailing period must be one_year, three_years, or five_years")
        start = (pd.Timestamp(end_date) - pd.DateOffset(years=PERIOD_YEARS[period])).date()
        return cls(instrument, instrument_type, start, end_date, period)


@dataclass
class MarketPriceFrame:
    """Market observations plus portable source and governance metadata."""

    data: pd.DataFrame
    instrument: str
    provider: str
    requested_start_date: date
    requested_end_date: date
    fields: list[str]
    instrument_type: str = "uploaded_instrument"
    price_basis: str = "unadjusted"
    retrieval_time: datetime = field(default_factory=lambda: datetime.now(UTC))
    raw_source_sha256: str | None = None
    missing_dates: list[str] = field(default_factory=list)
    cache_reference: str | None = None
    source_is_synthetic: bool = False
    redistribution_permitted: bool = False
    provider_terms: str | None = None
    notes: list[str] = field(default_factory=list)

    def metadata(self) -> dict[str, Any]:
        return {
            "instrument": self.instrument,
            "instrument_type": self.instrument_type,
            "provider": self.provider,
            "requested_start_date": self.requested_start_date.isoformat(),
            "requested_end_date": self.requested_end_date.isoformat(),
            "retrieval_time": self.retrieval_time.astimezone(UTC).isoformat(),
            "fields": list(self.fields),
            "price_basis": self.price_basis,
            "raw_source_sha256": self.raw_source_sha256,
            "missing_dates": list(self.missing_dates),
            "cache_reference": self.cache_reference,
            "source_is_synthetic": self.source_is_synthetic,
            "redistribution_permitted": self.redistribution_permitted,
            "provider_terms": self.provider_terms,
            "notes": list(self.notes),
        }


@runtime_checkable
class MarketDataProvider(Protocol):
    """Provider contract used by the Market Risk and Volatility Lab."""

    def get_prices(
        self,
        instrument: str,
        start_date: date,
        end_date: date,
        fields: list[str],
    ) -> MarketPriceFrame: ...


def validate_instrument(
    instrument: str,
    instrument_type: str,
    start_date: date,
    end_date: date,
) -> None:
    """Reject ambiguous identifiers, unsupported types, and unsafe date ranges."""

    if instrument_type not in INSTRUMENT_TYPES:
        raise MarketDataError(f"Unsupported instrument type: {instrument_type}")
    if not _INSTRUMENT_PATTERN.fullmatch(instrument.strip()):
        raise MarketDataError("Instrument contains unsupported characters or has invalid length")
    if start_date > end_date:
        raise MarketDataError("start_date must be on or before end_date")
    if (end_date - start_date).days > 366 * 10:
        raise MarketDataError("Analysis periods are limited to ten years")


def validate_fields(fields: list[str]) -> list[str]:
    if not fields:
        raise MarketDataError("At least one market-data field is required")
    normalised = list(dict.fromkeys(field.strip().lower() for field in fields))
    unsupported = sorted(set(normalised).difference(ALLOWED_FIELDS))
    if unsupported:
        raise MarketDataError(f"Unsupported market-data fields: {unsupported}")
    return normalised


def _frame_sha256(frame: pd.DataFrame) -> str:
    canonical = frame.to_csv(index=False, date_format="%Y-%m-%dT%H:%M:%S.%fZ").encode()
    return hashlib.sha256(canonical).hexdigest()


def _missing_business_dates(frame: pd.DataFrame, start_date: date, end_date: date) -> list[str]:
    if frame.empty:
        return [value.date().isoformat() for value in pd.bdate_range(start_date, end_date)]
    observed = set(pd.to_datetime(frame["date"], utc=True).dt.normalize())
    return [
        value.date().isoformat()
        for value in pd.bdate_range(start_date, end_date, tz="UTC")
        if value.normalize() not in observed
    ]


class DeterministicSampleProvider:
    """Bundled, synthetic OHLC provider that needs no network connection."""

    supported_instruments = {
        "NAIM-DEMO-INDEX": "index",
        "NAIM-DEMO-EQUITY": "equity",
    }

    def __init__(self, *, seed: int = 73421) -> None:
        self.seed = int(seed)

    def get_prices(
        self,
        instrument: str,
        start_date: date,
        end_date: date,
        fields: list[str],
    ) -> MarketPriceFrame:
        requested = validate_fields(fields)
        instrument_type = self.supported_instruments.get(instrument)
        if instrument_type is None:
            raise MarketDataError(
                f"Bundled provider supports only {sorted(self.supported_instruments)}"
            )
        validate_instrument(instrument, instrument_type, start_date, end_date)
        dates = pd.bdate_range(start_date, end_date, tz="UTC")
        if len(dates) < 3:
            raise MarketDataError("At least three business-day observations are required")
        instrument_seed = int(hashlib.sha256(instrument.encode()).hexdigest()[:8], 16)
        rng = np.random.default_rng(self.seed + instrument_seed)
        innovations = rng.standard_t(df=7, size=len(dates))
        conditional_sigma = np.empty(len(dates), dtype=float)
        conditional_sigma[0] = 0.009 if instrument_type == "index" else 0.014
        for position in range(1, len(dates)):
            shock = abs(innovations[position - 1])
            conditional_sigma[position] = (
                0.0008
                + 0.90 * conditional_sigma[position - 1]
                + 0.018 * shock * conditional_sigma[position - 1]
            )
        cycle = 0.00025 * np.sin(np.arange(len(dates)) * 2 * np.pi / 63)
        returns = 0.00018 + cycle + innovations * conditional_sigma / np.sqrt(7 / 5)
        close = 100.0 * np.exp(np.cumsum(returns))
        overnight = rng.normal(0, 0.0025, len(dates))
        open_price = close * np.exp(-returns + overnight)
        span = np.abs(rng.normal(0.008, 0.003, len(dates)))
        high = np.maximum(open_price, close) * (1 + span)
        low = np.minimum(open_price, close) * np.maximum(1 - span, 0.01)
        adjusted_close = close.copy()
        volume = rng.integers(800_000, 5_000_000, len(dates))
        complete = pd.DataFrame(
            {
                "date": dates,
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "adjusted_close": adjusted_close,
                "volume": volume,
            }
        )
        available = [field for field in requested if field in complete.columns]
        if "return" in requested:
            complete["return"] = complete["adjusted_close"].pct_change()
            available.append("return")
        data = complete[["date", *available]].copy()
        return MarketPriceFrame(
            data=data,
            instrument=instrument,
            instrument_type=instrument_type,
            provider="bundled_deterministic_sample",
            requested_start_date=start_date,
            requested_end_date=end_date,
            fields=available,
            price_basis="adjusted_close equals unadjusted close; no corporate actions simulated",
            raw_source_sha256=_frame_sha256(data),
            missing_dates=[],
            source_is_synthetic=True,
            redistribution_permitted=True,
            provider_terms="Bundled synthetic data; not observed market data.",
            notes=[
                "Deterministic educational sample.",
                "Not suitable for trading, valuation, or investment decisions.",
            ],
        )


class UploadedFileProvider:
    """Read a user-controlled CSV or XLSX file with a strict tabular contract."""

    def __init__(
        self,
        source_path: str | Path,
        *,
        instrument_type: str = "uploaded_instrument",
        price_basis: str = "user_declared_unadjusted",
        max_bytes: int = 50_000_000,
    ) -> None:
        self.source_path = Path(source_path).expanduser().resolve()
        self.instrument_type = instrument_type
        self.price_basis = price_basis
        self.max_bytes = int(max_bytes)

    def _load(self) -> tuple[pd.DataFrame, str]:
        if not self.source_path.is_file():
            raise MarketDataError("Uploaded market-data file does not exist")
        if self.source_path.stat().st_size > self.max_bytes:
            raise MarketDataError(f"Uploaded file exceeds {self.max_bytes} bytes")
        suffix = self.source_path.suffix.casefold()
        if suffix == ".csv":
            frame = pd.read_csv(self.source_path)
        elif suffix in {".xlsx", ".xlsm"}:
            frame = pd.read_excel(self.source_path)
        else:
            raise MarketDataError("Uploaded provider accepts CSV, XLSX, or XLSM only")
        raw_hash = hashlib.sha256(self.source_path.read_bytes()).hexdigest()
        frame.columns = [str(column).strip().lower().replace(" ", "_") for column in frame.columns]
        aliases = {"timestamp": "date", "datetime": "date", "adj_close": "adjusted_close"}
        frame = frame.rename(columns={key: value for key, value in aliases.items() if key in frame})
        if "date" not in frame:
            raise MarketDataError("Uploaded market data must include a date column")
        frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="coerce")
        if frame["date"].isna().any():
            raise MarketDataError("Uploaded market data contains invalid dates")
        return frame.sort_values("date").drop_duplicates("date", keep="last"), raw_hash

    def get_prices(
        self,
        instrument: str,
        start_date: date,
        end_date: date,
        fields: list[str],
    ) -> MarketPriceFrame:
        requested = validate_fields(fields)
        validate_instrument(instrument, self.instrument_type, start_date, end_date)
        frame, raw_hash = self._load()
        missing_fields = sorted(set(requested).difference(frame.columns))
        if missing_fields:
            raise MarketDataError(f"Uploaded file is missing requested fields: {missing_fields}")
        dates = frame["date"].dt.date
        selected = frame.loc[
            (dates >= start_date) & (dates <= end_date), ["date", *requested]
        ].copy()
        if len(selected) < 3:
            raise MarketDataError("Selected upload period has fewer than three observations")
        missing_dates = _missing_business_dates(selected, start_date, end_date)
        return MarketPriceFrame(
            data=selected,
            instrument=instrument,
            instrument_type=self.instrument_type,
            provider="uploaded_file",
            requested_start_date=start_date,
            requested_end_date=end_date,
            fields=requested,
            price_basis=self.price_basis,
            raw_source_sha256=raw_hash,
            missing_dates=missing_dates,
            cache_reference=f"sha256:{raw_hash}",
            source_is_synthetic=False,
            redistribution_permitted=False,
            provider_terms="User-supplied data; redistribution permission was not established.",
            notes=["The caller remains responsible for source rights and corporate-action basis."],
        )


@dataclass(frozen=True)
class ExternalProviderConfiguration:
    """Configuration metadata for an external provider; contains no credentials."""

    provider_name: str
    cache_directory: Path
    terms_url: str
    adjusted_price_field: str = "adjusted_close"
    enabled: bool = False


class ConfiguredExternalProvider:
    """Honest configuration-only adapter for a future licensed data connector."""

    def __init__(self, configuration: ExternalProviderConfiguration) -> None:
        self.configuration = configuration

    def get_prices(
        self,
        instrument: str,
        start_date: date,
        end_date: date,
        fields: list[str],
    ) -> MarketPriceFrame:
        validate_fields(fields)
        validate_instrument(instrument, "equity", start_date, end_date)
        state = "enabled but connector not installed" if self.configuration.enabled else "disabled"
        raise ExternalProviderUnavailable(
            f"External provider {self.configuration.provider_name!r} is {state}; "
            "configure a licensed connector before requesting data"
        )


class StaticMarketDataProvider:
    """Small deterministic provider for unit and contract tests."""

    def __init__(self, frame: pd.DataFrame, *, provider_name: str = "static_test_provider") -> None:
        self.frame = frame.copy()
        self.provider_name = provider_name

    def get_prices(
        self,
        instrument: str,
        start_date: date,
        end_date: date,
        fields: list[str],
    ) -> MarketPriceFrame:
        requested = validate_fields(fields)
        validate_instrument(instrument, "uploaded_instrument", start_date, end_date)
        frame = self.frame.copy()
        frame["date"] = pd.to_datetime(frame["date"], utc=True)
        selected = frame.loc[
            (frame["date"].dt.date >= start_date) & (frame["date"].dt.date <= end_date),
            ["date", *requested],
        ]
        return MarketPriceFrame(
            selected.reset_index(drop=True),
            instrument,
            self.provider_name,
            start_date,
            end_date,
            requested,
            missing_dates=_missing_business_dates(selected, start_date, end_date),
            raw_source_sha256=_frame_sha256(selected),
            redistribution_permitted=False,
            notes=["Static provider intended for controlled tests."],
        )
