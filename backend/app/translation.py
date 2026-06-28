from __future__ import annotations

import base64
import hmac
import hashlib
import json
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from .config import Settings
from .database import Database
from .schemas import TranslationItem, TranslationResponse


LANGUAGE_ALIASES = {
    "zh": "zh-CN",
    "zh-cn": "zh-CN",
    "chinese": "zh-CN",
    "en": "en",
    "english": "en",
}


def normalize_target_language(value: str) -> str:
    return LANGUAGE_ALIASES.get(value.strip().lower(), value.strip().lower())


def detect_language(text: str) -> str:
    if re.search(r"[\u3040-\u30ff]", text):
        return "ja"
    if re.search(r"[\uac00-\ud7af]", text):
        return "ko"
    if re.search(r"[\u4e00-\u9fff]", text):
        return "zh-CN"
    return "en"


def same_language(source: str, target: str) -> bool:
    if source.startswith("zh") and target.startswith("zh"):
        return True
    return source == target


class TranslationQuotaExhausted(Exception):
    pass


class TranslationProviderError(Exception):
    pass


@dataclass(frozen=True)
class ProviderResult:
    translated_text: str
    used_characters: int


@dataclass(frozen=True)
class ProviderRuntimeConfig:
    name: str
    char_budget: int | None
    quota_period: str
    requests_per_second: float


def _chars(text: str) -> int:
    return len(text)


def _provider_lang(language: str) -> str:
    return "zh" if language.startswith("zh") else language


def _azure_lang(language: str) -> str:
    return "zh-Hans" if language.startswith("zh") else language


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _sha256_hex(value: str | bytes) -> str:
    payload = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(payload).hexdigest()


def _hmac_sha256(key: bytes, value: str) -> bytes:
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).digest()


def _percent_encode(value: str) -> str:
    return quote(value, safe="~")


class TranslationProvider:
    name = ""

    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def runtime(self) -> ProviderRuntimeConfig:
        raise NotImplementedError

    def is_configured(self) -> bool:
        return self.runtime.char_budget is not None

    async def translate(self, text: str, source_language: str, target_language: str) -> ProviderResult:
        raise NotImplementedError


class MyMemoryProvider(TranslationProvider):
    name = "mymemory"

    @property
    def runtime(self) -> ProviderRuntimeConfig:
        return ProviderRuntimeConfig(
            name=self.name,
            char_budget=self.settings.mymemory_daily_char_budget,
            quota_period="daily",
            requests_per_second=self.settings.mymemory_requests_per_second,
        )

    async def translate(self, text: str, source_language: str, target_language: str) -> ProviderResult:
        params = {
            "q": text[:500],
            "langpair": f"{source_language}|{target_language}",
        }
        if self.settings.mymemory_email:
            params["de"] = self.settings.mymemory_email
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                response = await client.get(self.settings.mymemory_endpoint, params=params)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise TranslationProviderError(str(exc)) from exc

        translated = str((payload.get("responseData") or {}).get("translatedText") or "").strip()
        if not translated:
            raise TranslationProviderError("MyMemory returned an empty translation")
        return ProviderResult(translated_text=translated, used_characters=_chars(text))


class TencentProvider(TranslationProvider):
    name = "tencent"
    service = "tmt"
    action = "TextTranslate"
    version = "2018-03-21"

    @property
    def runtime(self) -> ProviderRuntimeConfig:
        return ProviderRuntimeConfig(
            name=self.name,
            char_budget=self.settings.tencent_translate_monthly_char_budget,
            quota_period="monthly",
            requests_per_second=self.settings.tencent_translate_requests_per_second,
        )

    def is_configured(self) -> bool:
        return bool(self.settings.tencent_translate_secret_id and self.settings.tencent_translate_secret_key and self.runtime.char_budget is not None)

    async def translate(self, text: str, source_language: str, target_language: str) -> ProviderResult:
        endpoint = self.settings.tencent_translate_endpoint
        host = urlparse(endpoint).netloc or endpoint.replace("https://", "").replace("http://", "")
        timestamp = int(time.time())
        date = datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d")
        payload = {
            "SourceText": text,
            "Source": _provider_lang(source_language),
            "Target": _provider_lang(target_language),
            "ProjectId": self.settings.tencent_translate_project_id,
        }
        body = _json_dumps(payload)
        canonical_headers = f"content-type:application/json; charset=utf-8\nhost:{host}\n"
        signed_headers = "content-type;host"
        canonical_request = "\n".join(["POST", "/", "", canonical_headers, signed_headers, _sha256_hex(body)])
        credential_scope = f"{date}/{self.service}/tc3_request"
        string_to_sign = "\n".join(["TC3-HMAC-SHA256", str(timestamp), credential_scope, _sha256_hex(canonical_request)])
        secret_date = _hmac_sha256(("TC3" + self.settings.tencent_translate_secret_key).encode("utf-8"), date)
        secret_service = _hmac_sha256(secret_date, self.service)
        secret_signing = _hmac_sha256(secret_service, "tc3_request")
        signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        authorization = (
            f"TC3-HMAC-SHA256 Credential={self.settings.tencent_translate_secret_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        headers = {
            "Authorization": authorization,
            "Content-Type": "application/json; charset=utf-8",
            "Host": host,
            "X-TC-Action": self.action,
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Version": self.version,
            "X-TC-Region": self.settings.tencent_translate_region,
        }
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                response = await client.post(endpoint, content=body.encode("utf-8"), headers=headers)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise TranslationProviderError(str(exc)) from exc
        data = payload.get("Response") or {}
        if data.get("Error"):
            raise TranslationProviderError(str(data["Error"]))
        translated = str(data.get("TargetText") or "").strip()
        if not translated:
            raise TranslationProviderError("Tencent returned an empty translation")
        return ProviderResult(translated_text=translated, used_characters=_chars(text))


class AliyunProvider(TranslationProvider):
    name = "aliyun"

    @property
    def runtime(self) -> ProviderRuntimeConfig:
        return ProviderRuntimeConfig(
            name=self.name,
            char_budget=self.settings.aliyun_translate_monthly_char_budget,
            quota_period="monthly",
            requests_per_second=self.settings.aliyun_translate_requests_per_second,
        )

    def is_configured(self) -> bool:
        return bool(
            self.settings.aliyun_translate_access_key_id
            and self.settings.aliyun_translate_access_key_secret
            and self.runtime.char_budget is not None
        )

    async def translate(self, text: str, source_language: str, target_language: str) -> ProviderResult:
        endpoint = self.settings.aliyun_translate_endpoint
        endpoint_url = endpoint if endpoint.startswith(("http://", "https://")) else f"https://{endpoint}/"
        params = {
            "AccessKeyId": self.settings.aliyun_translate_access_key_id or "",
            "Action": "TranslateGeneral",
            "Format": "JSON",
            "RegionId": self.settings.aliyun_translate_region,
            "Scene": self.settings.aliyun_translate_scene,
            "SignatureMethod": "HMAC-SHA1",
            "SignatureNonce": str(uuid.uuid4()),
            "SignatureVersion": "1.0",
            "SourceLanguage": _provider_lang(source_language),
            "SourceText": text,
            "TargetLanguage": _provider_lang(target_language),
            "Timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "Version": "2018-10-12",
        }
        canonical_query = "&".join(f"{_percent_encode(key)}={_percent_encode(str(params[key]))}" for key in sorted(params))
        string_to_sign = f"GET&%2F&{_percent_encode(canonical_query)}"
        key = f"{self.settings.aliyun_translate_access_key_secret}&".encode("utf-8")
        signature = base64.b64encode(hmac.new(key, string_to_sign.encode("utf-8"), hashlib.sha1).digest()).decode("utf-8")
        params["Signature"] = signature
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                response = await client.get(endpoint_url, params=params)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise TranslationProviderError(str(exc)) from exc
        translated = str((payload.get("Data") or {}).get("Translated") or "").strip()
        if not translated:
            raise TranslationProviderError(str(payload.get("Message") or "Aliyun returned an empty translation"))
        return ProviderResult(translated_text=translated, used_characters=_chars(text))


class VolcengineProvider(TranslationProvider):
    name = "volcengine"
    service = "translate"

    @property
    def runtime(self) -> ProviderRuntimeConfig:
        return ProviderRuntimeConfig(
            name=self.name,
            char_budget=self.settings.volcengine_translate_monthly_char_budget,
            quota_period="monthly",
            requests_per_second=self.settings.volcengine_translate_requests_per_second,
        )

    def is_configured(self) -> bool:
        return bool(
            self.settings.volcengine_translate_access_key_id
            and self.settings.volcengine_translate_secret_access_key
            and self.runtime.char_budget is not None
        )

    async def translate(self, text: str, source_language: str, target_language: str) -> ProviderResult:
        endpoint = self.settings.volcengine_translate_endpoint.rstrip("/")
        parsed = urlparse(endpoint)
        host = parsed.netloc
        now = datetime.now(timezone.utc)
        x_date = now.strftime("%Y%m%dT%H%M%SZ")
        date = now.strftime("%Y%m%d")
        query = "Action=TranslateText&Version=2020-06-01"
        body = _json_dumps(
            {
                "SourceLanguage": _provider_lang(source_language),
                "TargetLanguage": _provider_lang(target_language),
                "TextList": [text],
            }
        )
        body_hash = _sha256_hex(body)
        canonical_headers = f"host:{host}\nx-date:{x_date}\n"
        signed_headers = "host;x-date"
        canonical_request = "\n".join(["POST", "/", query, canonical_headers, signed_headers, body_hash])
        credential_scope = f"{date}/{self.settings.volcengine_translate_region}/{self.service}/request"
        string_to_sign = "\n".join(["HMAC-SHA256", x_date, credential_scope, _sha256_hex(canonical_request)])
        secret_date = _hmac_sha256(self.settings.volcengine_translate_secret_access_key.encode("utf-8"), date)
        secret_region = _hmac_sha256(secret_date, self.settings.volcengine_translate_region)
        secret_service = _hmac_sha256(secret_region, self.service)
        signing_key = _hmac_sha256(secret_service, "request")
        signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        authorization = (
            f"HMAC-SHA256 Credential={self.settings.volcengine_translate_access_key_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                response = await client.post(
                    f"{endpoint}/?{query}",
                    content=body.encode("utf-8"),
                    headers={
                        "Authorization": authorization,
                        "Content-Type": "application/json",
                        "Host": host,
                        "X-Date": x_date,
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise TranslationProviderError(str(exc)) from exc
        response_data = payload.get("ResponseMetadata") or {}
        if response_data.get("Error"):
            raise TranslationProviderError(str(response_data["Error"]))
        translated = ""
        translations = payload.get("TranslationList") or (payload.get("Result") or {}).get("TranslationList") or []
        if translations:
            translated = str(translations[0].get("Translation") or translations[0].get("TranslatedText") or "").strip()
        if not translated:
            raise TranslationProviderError("Volcengine returned an empty translation")
        return ProviderResult(translated_text=translated, used_characters=_chars(text))


class AzureProvider(TranslationProvider):
    name = "azure"

    @property
    def runtime(self) -> ProviderRuntimeConfig:
        return ProviderRuntimeConfig(
            name=self.name,
            char_budget=self.settings.azure_translator_monthly_char_budget,
            quota_period="monthly",
            requests_per_second=self.settings.azure_translator_requests_per_second,
        )

    def is_configured(self) -> bool:
        return bool(self.settings.azure_translator_key and self.runtime.char_budget is not None)

    async def translate(self, text: str, source_language: str, target_language: str) -> ProviderResult:
        endpoint = self.settings.azure_translator_endpoint.rstrip("/")
        params = {
            "api-version": "3.0",
            "from": _azure_lang(source_language),
            "to": _azure_lang(target_language),
        }
        headers = {
            "Content-Type": "application/json",
            "Ocp-Apim-Subscription-Key": self.settings.azure_translator_key or "",
            "X-ClientTraceId": str(uuid.uuid4()),
        }
        if self.settings.azure_translator_region:
            headers["Ocp-Apim-Subscription-Region"] = self.settings.azure_translator_region
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                response = await client.post(f"{endpoint}/translate", params=params, json=[{"text": text}], headers=headers)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise TranslationProviderError(str(exc)) from exc
        translated = ""
        if payload and payload[0].get("translations"):
            translated = str(payload[0]["translations"][0].get("text") or "").strip()
        if not translated:
            raise TranslationProviderError("Azure returned an empty translation")
        return ProviderResult(translated_text=translated, used_characters=_chars(text))


class TranslationService:
    def __init__(self, database: Database, settings: Settings):
        self.database = database
        self.settings = settings
        self._providers = self._make_providers()
        self._last_request_at: dict[str, float] = {}

    async def translate(self, texts: list[str], target_language: str) -> TranslationResponse:
        normalized_target = normalize_target_language(target_language)
        unique_texts = list(dict.fromkeys(text.strip() for text in texts if text and text.strip()))
        items: list[TranslationItem] = []
        providers_used_in_request: set[str] = set()
        for text in unique_texts[:160]:
            source_language = detect_language(text)
            translated = text
            if not same_language(source_language, normalized_target):
                translated = await self._translate_one(text, source_language, normalized_target, providers_used_in_request)
            items.append(
                TranslationItem(
                    original_text=text,
                    translated_text=translated,
                    source_language=source_language,
                    target_language=normalized_target,
                )
            )
        return TranslationResponse(target_language=normalized_target, items=items)

    async def _translate_one(self, text: str, source_language: str, target_language: str, providers_used_in_request: set[str]) -> str:
        cache_key = self._cache_key(text, source_language, target_language)
        cached = self._read_cache(cache_key)
        if cached is not None:
            return cached

        estimated_characters = _chars(text)
        for provider in self._providers:
            runtime = provider.runtime
            if not provider.is_configured():
                continue
            if not self._within_budget(runtime, estimated_characters):
                continue
            if self._rate_limited(runtime, providers_used_in_request):
                continue
            try:
                result = await provider.translate(text, source_language, target_language)
            except TranslationProviderError:
                self._record_failure(runtime.name)
                continue

            self._record_success(runtime.name, result.used_characters or estimated_characters)
            self._write_cache(cache_key, source_language, target_language, text, result.translated_text, runtime.name)
            return result.translated_text

        raise TranslationQuotaExhausted()

    def _make_providers(self) -> list[TranslationProvider]:
        registry: dict[str, type[TranslationProvider]] = {
            "mymemory": MyMemoryProvider,
            "tencent": TencentProvider,
            "aliyun": AliyunProvider,
            "volcengine": VolcengineProvider,
            "azure": AzureProvider,
        }
        providers: list[TranslationProvider] = []
        for name in self.settings.translation_providers:
            provider_class = registry.get(name)
            if provider_class:
                providers.append(provider_class(self.settings))
        return providers

    def _quota_key(self, runtime: ProviderRuntimeConfig) -> str:
        try:
            tz = ZoneInfo(self.settings.translation_billing_timezone)
        except ZoneInfoNotFoundError:
            if self.settings.translation_billing_timezone == "Asia/Shanghai":
                tz = timezone(timedelta(hours=8), "Asia/Shanghai")
            else:
                tz = timezone.utc
        now = datetime.now(tz)
        if runtime.quota_period == "daily":
            return now.strftime("%Y-%m-%d")
        return now.strftime("%Y-%m")

    def _within_budget(self, runtime: ProviderRuntimeConfig, estimated_characters: int) -> bool:
        if runtime.char_budget is None or runtime.char_budget <= 0:
            return False
        stop_limit = int(runtime.char_budget * self.settings.translation_stop_at_ratio)
        if stop_limit <= 0:
            return False
        used = self._read_usage(runtime)
        return used + estimated_characters <= stop_limit

    def _rate_limited(self, runtime: ProviderRuntimeConfig, providers_used_in_request: set[str]) -> bool:
        if runtime.name in providers_used_in_request:
            return False
        if runtime.requests_per_second <= 0:
            providers_used_in_request.add(runtime.name)
            return False
        now = time.monotonic()
        minimum_interval = 1 / runtime.requests_per_second
        last_request_at = self._last_request_at.get(runtime.name)
        if last_request_at is not None and now - last_request_at < minimum_interval:
            return True
        self._last_request_at[runtime.name] = now
        providers_used_in_request.add(runtime.name)
        return False

    def _cache_key(self, text: str, source_language: str, target_language: str) -> str:
        digest = hashlib.sha256(f"{source_language}|{target_language}|{text}".encode("utf-8")).hexdigest()
        return digest

    def _read_cache(self, cache_key: str) -> str | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT translated_text FROM translation_cache WHERE cache_key = ?", (cache_key,)).fetchone()
            return row["translated_text"] if row else None

    def _write_cache(self, cache_key: str, source_language: str, target_language: str, original_text: str, translated_text: str, provider: str) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO translation_cache
                (cache_key, source_language, target_language, original_text, translated_text, provider, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cache_key,
                    source_language,
                    target_language,
                    original_text,
                    translated_text,
                    provider,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def _read_usage(self, runtime: ProviderRuntimeConfig) -> int:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT used_characters
                FROM translation_usage_monthly
                WHERE provider = ? AND year_month = ?
                """,
                (runtime.name, self._quota_key(runtime)),
            ).fetchone()
            return int(row["used_characters"]) if row else 0

    def _record_success(self, provider: str, used_characters: int) -> None:
        runtime = self._runtime_for_provider(provider)
        if runtime:
            self._upsert_usage(runtime, used_characters=used_characters, request_count=1, failed_count=0)

    def _record_failure(self, provider: str) -> None:
        runtime = self._runtime_for_provider(provider)
        if runtime:
            self._upsert_usage(runtime, used_characters=0, request_count=1, failed_count=1)

    def _runtime_for_provider(self, provider: str) -> ProviderRuntimeConfig | None:
        for configured_provider in self._providers:
            if configured_provider.runtime.name == provider:
                return configured_provider.runtime
        return None

    def _upsert_usage(self, runtime: ProviderRuntimeConfig, used_characters: int, request_count: int, failed_count: int) -> None:
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO translation_usage_monthly
                (provider, year_month, used_characters, request_count, failed_count, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, year_month) DO UPDATE SET
                    used_characters = used_characters + excluded.used_characters,
                    request_count = request_count + excluded.request_count,
                    failed_count = failed_count + excluded.failed_count,
                    updated_at = excluded.updated_at
                """,
                (
                    runtime.name,
                    self._quota_key(runtime),
                    used_characters,
                    request_count,
                    failed_count,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
