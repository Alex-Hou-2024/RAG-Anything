"""Text and multimodal question-answering endpoints."""
from __future__ import annotations
from typing import Any, Literal
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from api.services.query import QueryError, QueryService
router=APIRouter(prefix='/query', tags=['query'])
_MODES={'naive','local','global','hybrid','mix'}
class QueryRequest(BaseModel):
    query:str=Field(min_length=1,max_length=20000)
    mode:str='hybrid'
    stream:bool=False
class MultimodalQueryRequest(QueryRequest):
    multimodal_content:list[dict[str,Any]]=Field(min_length=1,max_length=50)
def service(request:Request)->QueryService:return request.app.state.query_service
async def respond(payload:QueryRequest, request:Request, content:list[dict[str,Any]]|None=None)->Any:
    if payload.mode not in _MODES: raise HTTPException(422, detail='Unsupported query mode')
    try:
        if payload.stream:
            return StreamingResponse(service(request).stream(payload.query,payload.mode,content),media_type='text/event-stream',headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})
        return await service(request).answer(payload.query,payload.mode,content)
    except QueryError as error: raise HTTPException(503,detail=str(error)) from error
@router.post('')
async def query(payload:QueryRequest,request:Request)->Any:return await respond(payload,request)
@router.post('/multimodal')
async def multimodal_query(payload:MultimodalQueryRequest,request:Request)->Any:return await respond(payload,request,payload.multimodal_content)
