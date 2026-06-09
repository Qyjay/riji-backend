import asyncio
import json


def _reset_location_state(monkeypatch, tmp_path):
    from app.config import settings
    from app.location import service

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "AMAP_WEB_SERVICE_KEY", "test-amap-key")
    monkeypatch.setattr(settings, "AMAP_REVERSE_GEOCODE_MONTHLY_LIMIT", 150000)
    monkeypatch.setattr(settings, "AMAP_WEATHER_MONTHLY_LIMIT", 5000)
    monkeypatch.setattr(settings, "AMAP_LOCATION_CACHE_TTL_SEC", 1800)
    service._location_cache.clear()
    service._ip_location_cache.clear()
    asyncio.set_event_loop(asyncio.new_event_loop())
    monkeypatch.setattr(service, "usage_counter", service.AmapUsageCounter())
    return service


def test_location_context_queries_amap_and_uses_cache(monkeypatch, tmp_path):
    service = _reset_location_state(monkeypatch, tmp_path)
    calls = []

    async def fake_request_amap(path, params):
        calls.append((path, params))
        if path == "/geocode/regeo":
            return {
                "status": "1",
                "regeocode": {
                    "formatted_address": "天津市南开区卫津路94号",
                    "addressComponent": {
                        "province": "天津市",
                        "city": [],
                        "district": "南开区",
                        "township": "学府街道",
                        "adcode": "120104",
                        "citycode": "022",
                    },
                },
            }
        if path == "/weather/weatherInfo":
            return {
                "status": "1",
                "forecasts": [
                    {
                        "reporttime": "2026-06-08 10:00:00",
                        "casts": [
                            {
                                "dayweather": "晴",
                                "nightweather": "多云",
                                "daytemp": "25",
                                "nighttemp": "18",
                            }
                        ],
                    }
                ],
            }
        raise AssertionError(f"unexpected amap path: {path}")

    monkeypatch.setattr(service, "_request_amap", fake_request_amap)

    first = asyncio.run(service.get_location_context(39.10012, 117.20012))
    second = asyncio.run(service.get_location_context(39.10019, 117.20019))

    assert first["locationVisible"] is True
    assert first["weatherVisible"] is True
    assert first["address"] == "天津市南开区卫津路94号"
    assert first["district"] == "南开区"
    assert first["weatherText"] in {"晴 25℃", "多云 18℃"}
    assert first["weatherPeriods"] == [
        {"key": "morning", "label": "上午", "weatherText": "晴 25℃"},
        {"key": "afternoon", "label": "下午", "weatherText": "晴 25℃"},
        {"key": "evening", "label": "晚上", "weatherText": "多云 18℃"},
    ]
    assert second["weatherText"] == first["weatherText"]
    assert calls == [
        (
            "/geocode/regeo",
            {"location": "117.200120,39.100120", "extensions": "base", "radius": 1000},
        ),
        ("/weather/weatherInfo", {"city": "120104", "extensions": "all"}),
    ]

    usage = json.loads((tmp_path / ".usage" / "amap_usage.json").read_text(encoding="utf-8"))
    assert usage["counts"] == {"reverse_geocode": 1, "ip_location": 0, "weather": 1}


def test_ip_location_context_queries_amap_ip_and_weather(monkeypatch, tmp_path):
    service = _reset_location_state(monkeypatch, tmp_path)
    calls = []

    async def fake_request_amap(path, params):
        calls.append((path, params))
        if path == "/ip":
            return {
                "status": "1",
                "province": "天津市",
                "city": "天津市",
                "adcode": "120000",
            }
        if path == "/weather/weatherInfo":
            return {
                "status": "1",
                "forecasts": [
                    {
                        "reporttime": "2026-06-08 11:00:00",
                        "casts": [
                            {
                                "dayweather": "多云",
                                "nightweather": "阴",
                                "daytemp": "26",
                                "nighttemp": "21",
                            }
                        ],
                    }
                ],
            }
        raise AssertionError(f"unexpected amap path: {path}")

    monkeypatch.setattr(service, "_request_amap", fake_request_amap)

    first = asyncio.run(service.get_ip_location_context("1.2.3.4"))
    second = asyncio.run(service.get_ip_location_context("1.2.3.4"))

    assert first["source"] == "ip"
    assert first["locationVisible"] is True
    assert first["weatherVisible"] is True
    assert first["city"] == "天津市"
    assert first["weatherText"] in {"多云 26℃", "阴 21℃"}
    assert first["weatherPeriods"] == [
        {"key": "morning", "label": "上午", "weatherText": "多云 26℃"},
        {"key": "afternoon", "label": "下午", "weatherText": "多云 26℃"},
        {"key": "evening", "label": "晚上", "weatherText": "阴 21℃"},
    ]
    assert second["weatherText"] == first["weatherText"]
    assert calls == [
        ("/ip", {"ip": "1.2.3.4"}),
        ("/weather/weatherInfo", {"city": "120000", "extensions": "all"}),
    ]

    usage = json.loads((tmp_path / ".usage" / "amap_usage.json").read_text(encoding="utf-8"))
    assert usage["counts"] == {"reverse_geocode": 0, "ip_location": 1, "weather": 1}


def test_location_context_hides_address_after_reverse_limit(monkeypatch, tmp_path):
    service = _reset_location_state(monkeypatch, tmp_path)
    from app.config import settings

    monkeypatch.setattr(settings, "AMAP_REVERSE_GEOCODE_MONTHLY_LIMIT", 0)

    async def fake_request_amap(path, params):
        raise AssertionError("should not call amap after limit is reached")

    monkeypatch.setattr(service, "_request_amap", fake_request_amap)

    result = asyncio.run(service.get_location_context(39.1, 117.2))

    assert result["locationVisible"] is False
    assert result["weatherVisible"] is False
    assert result["address"] == ""
    assert result["weatherText"] == ""
    assert result["reverseGeocodeLimited"] is True
    assert result["weatherLimited"] is False


def test_location_context_hides_weather_after_weather_limit(monkeypatch, tmp_path):
    service = _reset_location_state(monkeypatch, tmp_path)
    from app.config import settings

    monkeypatch.setattr(settings, "AMAP_WEATHER_MONTHLY_LIMIT", 0)
    calls = []

    async def fake_request_amap(path, params):
        calls.append(path)
        if path == "/geocode/regeo":
            return {
                "status": "1",
                "regeocode": {
                    "formatted_address": "天津市南开区卫津路94号",
                    "addressComponent": {"district": "南开区", "adcode": "120104"},
                },
            }
        raise AssertionError("weather request should be skipped after limit is reached")

    monkeypatch.setattr(service, "_request_amap", fake_request_amap)

    result = asyncio.run(service.get_location_context(39.1, 117.2))

    assert result["locationVisible"] is True
    assert result["weatherVisible"] is False
    assert result["address"] == "天津市南开区卫津路94号"
    assert result["weatherText"] == ""
    assert result["reverseGeocodeLimited"] is False
    assert result["weatherLimited"] is True
    assert calls == ["/geocode/regeo"]
