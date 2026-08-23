"""RAG query adapter with normalized answers, citations, and SSE fallback."""
from __future__ import annotations
import inspect, json, logging
from collections.abc import AsyncIterator
from typing import Any
from api.deps import RAGService
logger=logging.getLogger(__name__)

class QueryError(RuntimeError): pass

class QueryService:
    def __init__(self, rag_service:RAGService)->None: self.rag_service=rag_service
    async def answer(self, query:str, mode:str, multimodal_content:list[dict[str,Any]]|None=None)->dict[str,Any]:
        if not self.rag_service.is_ready or self.rag_service.instance is None:
            raise QueryError('RAG backend is not ready; check /healthz')
        rag=self.rag_service.instance
        try:
            if multimodal_content is None:
                result=rag.aquery(query, mode=mode)
            else:
                result=rag.aquery_with_multimodal(query, multimodal_content=multimodal_content, mode=mode)
            if inspect.isawaitable(result): result=await result
            if hasattr(result, '__aiter__'):
                text=''.join([str(part) async for part in result])
            elif isinstance(result, dict): text=str(result.get('answer', result.get('response','')))
            else: text=str(result)
            citations=self._citations(result)
            return {'answer':text,'citations':citations}
        except QueryError: raise
        except Exception as error:
            logger.exception('RAG query failed')
            raise QueryError('Query processing failed') from error
    @staticmethod
    def _citations(result:Any)->list[dict[str,Any]]:
        if not isinstance(result,dict): return []
        raw=result.get('citations') or result.get('references') or []
        if not isinstance(raw,list): return []
        citations=[]
        for item in raw:
            if isinstance(item,dict):
                citations.append({'document_id':item.get('document_id') or item.get('doc_id'), 'kind':item.get('kind') or item.get('type','fragment'), 'id':item.get('id') or item.get('chunk_id'), 'preview':item.get('preview') or item.get('text')})
        return citations
    async def stream(self, query:str, mode:str, multimodal_content:list[dict[str,Any]]|None=None)->AsyncIterator[bytes]:
        # Existing RAG APIs may not stream; emit a standards-compliant single delta fallback.
        try:
            response=await self.answer(query,mode,multimodal_content)
            yield self._event('delta', {'text':response['answer']})
            yield self._event('citations', {'citations':response['citations']})
            yield self._event('done', {})
        except QueryError as error:
            yield self._event('error', {'message':str(error)})
    @staticmethod
    def _event(event:str,data:dict[str,Any])->bytes:
        return f'event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n'.encode()
