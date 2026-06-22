import os
import json
import logging
from typing import Dict, Any, Optional
from backend.core.config import get_llm, extract_json, get_course_path, format_docs
from backend.core.prompts import MINDMAP_PROMPT
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

logger = logging.getLogger(__name__)

class MindmapGenerator:
    def __init__(self, rag_chains):
        self.rag = rag_chains
        self.course_id = rag_chains.course_id
        self.vectorstore = rag_chains.vectorstore

    def generate_mindmap(self, max_depth: int = 3) -> Dict[str, Any]:
        """Tạo cấu trúc Mindmap JSON từ tài liệu."""
        self.rag._require_ready()
        retriever = self.vectorstore.as_retriever(search_kwargs={"k": 15})
        context_query = "cấu trúc tài liệu và các luận điểm chính hệ thống hóa"
        docs = retriever.invoke(context_query)
        context = format_docs(docs)
        citations = []
        for doc in docs:
            citations.append({
                "page": doc.metadata.get("page", "N/A"),
                "source": os.path.basename(doc.metadata.get("source", "unknown")),
                "chunk_id": f"chunk_{hash(doc.page_content) % 10000}"
            })
        llm = get_llm(temperature=0.2)
        prompt = ChatPromptTemplate.from_messages([
            ("system", MINDMAP_PROMPT),
            ("human", "Tạo bản đồ tư duy cho tài liệu này."),
        ])
        
        chain = prompt | llm | StrOutputParser()
        
        try:
            raw_res = chain.invoke({
                "context": context, 
                "max_depth": max_depth 
            })
            
            clean_json = extract_json(raw_res)
            mindmap_dict = json.loads(clean_json)

            final_response = {
                "course_id": self.course_id,
                "mindmap": mindmap_dict,
                "citations": citations[:5]
            }

            # Lưu file
            paths = get_course_path(self.course_id)
            save_dir = paths["mindmaps"]
            os.makedirs(save_dir, exist_ok=True)
            save_path = os.path.join(save_dir, "mindmap.json")
            
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(final_response, f, indent=2, ensure_ascii=False)
            
            return final_response
        except Exception as e:
            logger.error(f"Lỗi tạo Mindmap: {e}")
            raise RuntimeError(f"Không thể tạo bản đồ tư duy: {str(e)}")