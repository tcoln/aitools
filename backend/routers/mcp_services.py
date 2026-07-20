import json
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas.mcp_service import MCPServiceCreate, MCPServiceUpdate, MCPServiceResponse
from models.mcp_service import MCPService
from models.user import User
from services.mcp_client import mcp_client_manager
from routers.auth import get_current_user, require_admin

router = APIRouter(prefix="/api/mcp-services", tags=["mcp_services"])


@router.get("/", response_model=list[MCPServiceResponse])
async def list_services(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MCPService).order_by(MCPService.created_at.desc())
    )
    services = result.scalars().all()
    return [MCPServiceResponse.model_validate(s) for s in services]


@router.get("/{service_id}", response_model=MCPServiceResponse)
async def get_service(
    service_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(MCPService).where(MCPService.id == service_id))
    service = result.scalar_one_or_none()
    if not service:
        raise HTTPException(status_code=404, detail="MCP服务不存在")
    return MCPServiceResponse.model_validate(service)


@router.post("/", response_model=MCPServiceResponse, status_code=status.HTTP_201_CREATED)
async def create_service(
    data: MCPServiceCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(
        select(MCPService).where(MCPService.name == data.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="MCP服务名称已存在")

    service = MCPService(
        name=data.name,
        description=data.description,
        transport_type=data.transport_type,
        command=data.command,
        args=data.args,
        env_vars=data.env_vars,
        url=data.url,
        headers=data.headers,
        is_active=True,
    )
    db.add(service)
    await db.commit()
    await db.refresh(service)
    return MCPServiceResponse.model_validate(service)


@router.put("/{service_id}", response_model=MCPServiceResponse)
async def update_service(
    service_id: str,
    data: MCPServiceUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(MCPService).where(MCPService.id == service_id))
    service = result.scalar_one_or_none()
    if not service:
        raise HTTPException(status_code=404, detail="MCP服务不存在")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(service, key, value)

    await db.commit()
    await db.refresh(service)
    return MCPServiceResponse.model_validate(service)


@router.delete("/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(
    service_id: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(MCPService).where(MCPService.id == service_id))
    service = result.scalar_one_or_none()
    if not service:
        raise HTTPException(status_code=404, detail="MCP服务不存在")

    await db.delete(service)
    await db.commit()


@router.post("/{service_id}/test")
async def test_service(
    service_id: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(MCPService).where(MCPService.id == service_id))
    service = result.scalar_one_or_none()
    if not service:
        raise HTTPException(status_code=404, detail="MCP服务不存在")

    config = {
        "name": service.name,
        "transport_type": service.transport_type,
        "command": service.command,
        "args": service.args,
        "env_vars": service.env_vars,
        "url": service.url,
        "headers": service.headers,
    }

    try:
        tools = await mcp_client_manager.get_tools(config)
        return {"success": True, "tools": tools, "tool_count": len(tools)}
    except Exception as e:
        return {"success": False, "error": str(e)}