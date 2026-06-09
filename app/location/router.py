from fastapi import APIRouter, Depends, Query, Request

from app.dependencies import get_current_user
from app.location.service import get_ip_location_context, get_location_context, usage_counter
from app.models.user import User
from app.response import success


router = APIRouter(prefix="/location", tags=["location"])


@router.get("/context", summary="根据经纬度获取地址与天气")
async def location_context(
    lat: float = Query(..., description="纬度"),
    lng: float = Query(..., description="经度"),
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    return success(await get_location_context(lat, lng))


def _client_ip_from_request(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    real_ip = request.headers.get("x-real-ip", "")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else ""


@router.get("/ip-context", summary="根据客户端 IP 获取城市级地址与天气")
async def ip_location_context(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    return success(await get_ip_location_context(_client_ip_from_request(request)))


@router.get("/amap-usage", summary="查看高德 Web 服务月度用量")
async def amap_usage(current_user: User = Depends(get_current_user)):
    _ = current_user
    return success(await usage_counter.snapshot())
