from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from zoneinfo import ZoneInfo

import httpx

from app.config import settings


logger = logging.getLogger(__name__)

AMAP_REVERSE_SERVICE = "reverse_geocode"
AMAP_IP_LOCATION_SERVICE = "ip_location"
AMAP_WEATHER_SERVICE = "weather"
AMAP_TZ = ZoneInfo("Asia/Shanghai")

_cache_lock = asyncio.Lock()
_location_cache: Dict[str, Tuple[float, dict]] = {}
_ip_location_cache: Dict[str, Tuple[float, dict]] = {}


def _current_period() -> str:
    return datetime.now(AMAP_TZ).strftime("%Y-%m")


def _usage_file_path() -> Path:
    usage_dir = Path(settings.UPLOAD_DIR) / ".usage"
    usage_dir.mkdir(parents=True, exist_ok=True)
    return usage_dir / "amap_usage.json"


class AmapUsageCounter:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._period = _current_period()
        self._counts = {
            AMAP_REVERSE_SERVICE: 0,
            AMAP_IP_LOCATION_SERVICE: 0,
            AMAP_WEATHER_SERVICE: 0,
        }
        self._loaded = False

    async def _load_locked(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        path = _usage_file_path()
        if not path.exists():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("[amap] usage file read failed, start from empty counter")
            return
        if raw.get("period") != self._period:
            return
        counts = raw.get("counts") if isinstance(raw, dict) else None
        if not isinstance(counts, dict):
            return
        for service in self._counts:
            try:
                self._counts[service] = max(0, int(counts.get(service) or 0))
            except Exception:
                self._counts[service] = 0

    def _limit_for(self, service: str) -> int:
        if service == AMAP_REVERSE_SERVICE:
            return max(0, int(settings.AMAP_REVERSE_GEOCODE_MONTHLY_LIMIT))
        if service == AMAP_IP_LOCATION_SERVICE:
            return max(0, int(settings.AMAP_IP_LOCATION_MONTHLY_LIMIT))
        if service == AMAP_WEATHER_SERVICE:
            return max(0, int(settings.AMAP_WEATHER_MONTHLY_LIMIT))
        return 0

    def _persist_locked(self) -> None:
        path = _usage_file_path()
        payload = {
            "period": self._period,
            "counts": self._counts,
            "updatedAt": int(time.time()),
        }
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(path)

    async def try_consume(self, service: str) -> bool:
        async with self._lock:
            period = _current_period()
            if period != self._period:
                self._period = period
                self._counts = {
                    AMAP_REVERSE_SERVICE: 0,
                    AMAP_IP_LOCATION_SERVICE: 0,
                    AMAP_WEATHER_SERVICE: 0,
                }
                self._loaded = True
                self._persist_locked()
            await self._load_locked()

            limit = self._limit_for(service)
            if limit <= 0 or self._counts.get(service, 0) >= limit:
                return False
            self._counts[service] = self._counts.get(service, 0) + 1
            self._persist_locked()
            return True

    async def snapshot(self) -> dict:
        async with self._lock:
            await self._load_locked()
            return {
                "period": self._period,
                "reverseGeocode": {
                    "used": self._counts.get(AMAP_REVERSE_SERVICE, 0),
                    "limit": self._limit_for(AMAP_REVERSE_SERVICE),
                },
                "ipLocation": {
                    "used": self._counts.get(AMAP_IP_LOCATION_SERVICE, 0),
                    "limit": self._limit_for(AMAP_IP_LOCATION_SERVICE),
                },
                "weather": {
                    "used": self._counts.get(AMAP_WEATHER_SERVICE, 0),
                    "limit": self._limit_for(AMAP_WEATHER_SERVICE),
                },
            }


usage_counter = AmapUsageCounter()


def _cache_key(lat: float, lng: float) -> str:
    # 约 100 米粒度，避免同一地点重复消耗高德额度。
    return f"{lat:.3f},{lng:.3f}"


def _is_private_or_local_ip(ip: str) -> bool:
    if not ip:
        return True
    if ip.startswith(("127.", "10.", "192.168.", "169.254.")):
        return True
    if ip.startswith("172."):
        parts = ip.split(".")
        if len(parts) > 1:
            try:
                return 16 <= int(parts[1]) <= 31
            except ValueError:
                return False
    return ip in {"::1", "localhost"}


def _safe_float(value: Any) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if result != result:
        return None
    return result


def _format_weather(live: dict) -> str:
    weather = str(live.get("weather") or "").strip()
    temperature = str(live.get("temperature") or "").strip()
    if weather and temperature:
        return f"{weather} {temperature}℃"
    return weather


def _format_forecast_weather(weather: str, temperature: str) -> str:
    weather_text = str(weather or "").strip()
    temp_text = str(temperature or "").strip()
    if weather_text and temp_text:
        return f"{weather_text} {temp_text}℃"
    return weather_text


def _build_weather_periods(cast: dict) -> list[dict]:
    day_weather = str(cast.get("dayweather") or "").strip()
    night_weather = str(cast.get("nightweather") or "").strip()
    day_temp = str(cast.get("daytemp") or "").strip()
    night_temp = str(cast.get("nighttemp") or "").strip()
    return [
        {"key": "morning", "label": "上午", "weatherText": _format_forecast_weather(day_weather, day_temp)},
        {"key": "afternoon", "label": "下午", "weatherText": _format_forecast_weather(day_weather, day_temp)},
        {"key": "evening", "label": "晚上", "weatherText": _format_forecast_weather(night_weather or day_weather, night_temp or day_temp)},
    ]


def _normalize_address_component(component: Any) -> dict:
    if not isinstance(component, dict):
        return {}

    def first_text(value: Any) -> str:
        if isinstance(value, list):
            value = value[0] if value else ""
        return str(value or "").strip()

    return {
        "province": first_text(component.get("province")),
        "city": first_text(component.get("city")),
        "district": first_text(component.get("district")),
        "township": first_text(component.get("township")),
        "adcode": first_text(component.get("adcode")),
        "citycode": first_text(component.get("citycode")),
    }


async def _request_amap(path: str, params: dict) -> dict:
    api_key = settings.AMAP_WEB_SERVICE_KEY.strip()
    if not api_key:
        return {}

    url = f"{settings.AMAP_BASE_URL.rstrip('/')}/{path.lstrip('/')}"
    request_params = {
        "key": api_key,
        "output": "JSON",
        **params,
    }
    try:
        async with httpx.AsyncClient(timeout=float(settings.AMAP_TIMEOUT_SEC), trust_env=False) as client:
            response = await client.get(url, params=request_params)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        logger.warning("[amap] request failed path=%s error=%s", path, str(exc))
        return {}

    if str(data.get("status")) != "1":
        logger.warning("[amap] non-success response path=%s info=%s infocode=%s", path, data.get("info"), data.get("infocode"))
        return {}
    return data


async def _reverse_geocode(lat: float, lng: float) -> dict:
    if not settings.AMAP_WEB_SERVICE_KEY.strip():
        return {"visible": False, "limited": False}
    if not await usage_counter.try_consume(AMAP_REVERSE_SERVICE):
        return {"visible": False, "limited": True}

    data = await _request_amap(
        "/geocode/regeo",
        {
            "location": f"{lng:.6f},{lat:.6f}",
            "extensions": "base",
            "radius": 1000,
        },
    )
    regeocode = data.get("regeocode") if isinstance(data, dict) else None
    if not isinstance(regeocode, dict):
        return {"visible": False, "limited": False}

    component = _normalize_address_component(regeocode.get("addressComponent"))
    address = str(regeocode.get("formatted_address") or "").strip()
    return {
        "visible": bool(address or component.get("adcode")),
        "limited": False,
        "address": address,
        **component,
    }


async def _query_weather(adcode: str) -> dict:
    if not adcode:
        return {"visible": False, "limited": False}
    if not settings.AMAP_WEB_SERVICE_KEY.strip():
        return {"visible": False, "limited": False}
    if not await usage_counter.try_consume(AMAP_WEATHER_SERVICE):
        return {"visible": False, "limited": True}

    data = await _request_amap(
        "/weather/weatherInfo",
        {
            "city": adcode,
            "extensions": "all",
        },
    )
    forecasts = data.get("forecasts") if isinstance(data, dict) else None
    forecast = forecasts[0] if isinstance(forecasts, list) and forecasts else None
    casts = forecast.get("casts") if isinstance(forecast, dict) else None
    cast = casts[0] if isinstance(casts, list) and casts else None
    if not isinstance(cast, dict):
        return {"visible": False, "limited": False}

    weather_periods = _build_weather_periods(cast)
    now_hour = datetime.now(AMAP_TZ).hour
    period_key = "morning" if now_hour < 12 else "afternoon" if now_hour < 18 else "evening"
    current_period = next((item for item in weather_periods if item["key"] == period_key), weather_periods[0])
    weather_text = str(current_period.get("weatherText") or "").strip()
    weather = weather_text.split(" ", 1)[0] if weather_text else ""
    return {
        "visible": bool(weather_text),
        "limited": False,
        "weather": weather,
        "temperature": "",
        "weatherText": weather_text,
        "weatherPeriods": weather_periods,
        "reportTime": str(forecast.get("reporttime") or "").strip(),
    }


async def _query_ip_location(ip: str) -> dict:
    if not settings.AMAP_WEB_SERVICE_KEY.strip():
        return {"visible": False, "limited": False}
    if _is_private_or_local_ip(ip):
        return {"visible": False, "limited": False}
    if not await usage_counter.try_consume(AMAP_IP_LOCATION_SERVICE):
        return {"visible": False, "limited": True}

    data = await _request_amap("/ip", {"ip": ip})
    adcode = str(data.get("adcode") or "").strip()
    province = str(data.get("province") or "").strip()
    city = str(data.get("city") or "").strip()
    if province == "[]":
        province = ""
    if city == "[]":
        city = ""
    address_parts = [province]
    if city and city != province:
        address_parts.append(city)
    address = " · ".join(part for part in address_parts if part)
    return {
        "visible": bool(adcode or address),
        "limited": False,
        "address": address,
        "province": province,
        "city": city,
        "district": "",
        "township": "",
        "adcode": adcode,
        "citycode": "",
    }


async def get_location_context(lat: Any, lng: Any) -> dict:
    latitude = _safe_float(lat)
    longitude = _safe_float(lng)
    if latitude is None or longitude is None:
        return {
            "locationVisible": False,
            "weatherVisible": False,
            "address": "",
            "weatherText": "",
            "usage": await usage_counter.snapshot(),
        }

    key = _cache_key(latitude, longitude)
    now = time.time()
    ttl = max(0, int(settings.AMAP_LOCATION_CACHE_TTL_SEC))
    async with _cache_lock:
        cached = _location_cache.get(key)
        if cached and ttl > 0 and now - cached[0] < ttl:
            return cached[1]

    location = await _reverse_geocode(latitude, longitude)
    weather = await _query_weather(str(location.get("adcode") or ""))
    result = {
        "locationVisible": bool(location.get("visible")),
        "weatherVisible": bool(weather.get("visible")),
        "address": str(location.get("address") or ""),
        "province": str(location.get("province") or ""),
        "city": str(location.get("city") or ""),
        "district": str(location.get("district") or ""),
        "township": str(location.get("township") or ""),
        "adcode": str(location.get("adcode") or ""),
        "lat": latitude,
        "lng": longitude,
        "weather": str(weather.get("weather") or ""),
        "temperature": str(weather.get("temperature") or ""),
        "weatherText": str(weather.get("weatherText") or ""),
        "weatherPeriods": weather.get("weatherPeriods") if isinstance(weather.get("weatherPeriods"), list) else [],
        "reportTime": str(weather.get("reportTime") or ""),
        "reverseGeocodeLimited": bool(location.get("limited")),
        "weatherLimited": bool(weather.get("limited")),
        "usage": await usage_counter.snapshot(),
    }

    async with _cache_lock:
        _location_cache[key] = (now, result)
    return result


async def get_ip_location_context(ip: str) -> dict:
    ip_text = str(ip or "").split(",", 1)[0].strip()
    if not ip_text:
        return {
            "locationVisible": False,
            "weatherVisible": False,
            "address": "",
            "weatherText": "",
            "ipLocationLimited": False,
            "weatherLimited": False,
            "usage": await usage_counter.snapshot(),
        }

    now = time.time()
    ttl = max(0, int(settings.AMAP_LOCATION_CACHE_TTL_SEC))
    cache_key = f"ip:{ip_text}"
    async with _cache_lock:
        cached = _ip_location_cache.get(cache_key)
        if cached and ttl > 0 and now - cached[0] < ttl:
            return cached[1]

    location = await _query_ip_location(ip_text)
    weather = await _query_weather(str(location.get("adcode") or ""))
    result = {
        "locationVisible": bool(location.get("visible")),
        "weatherVisible": bool(weather.get("visible")),
        "address": str(location.get("address") or ""),
        "province": str(location.get("province") or ""),
        "city": str(location.get("city") or ""),
        "district": str(location.get("district") or ""),
        "township": str(location.get("township") or ""),
        "adcode": str(location.get("adcode") or ""),
        "lat": None,
        "lng": None,
        "weather": str(weather.get("weather") or ""),
        "temperature": str(weather.get("temperature") or ""),
        "weatherText": str(weather.get("weatherText") or ""),
        "weatherPeriods": weather.get("weatherPeriods") if isinstance(weather.get("weatherPeriods"), list) else [],
        "reportTime": str(weather.get("reportTime") or ""),
        "ipLocationLimited": bool(location.get("limited")),
        "reverseGeocodeLimited": False,
        "weatherLimited": bool(weather.get("limited")),
        "source": "ip",
        "usage": await usage_counter.snapshot(),
    }

    async with _cache_lock:
        _ip_location_cache[cache_key] = (now, result)
    return result
