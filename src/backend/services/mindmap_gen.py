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

    def generate_mindmap(self) -> Dict[str, Any]:
        """Tạo cấu trúc Mindmap JSON từ tài liệu."""
        self.rag._require_ready()
        
        # Lấy các đoạn văn bản quan trọng nhất (k=15)
        retriever = self.vectorstore.as_retriever(search_kwargs={"k": 15})
        # Dùng hàm lambda để định danh text tìm kiếm giống các feature khác
        context_query = "cấu trúc tài liệu và các luận điểm chính hệ thống hóa"
        docs = retriever.invoke(context_query)
        context = format_docs(docs)

        llm = get_llm(temperature=0.2)
        prompt = ChatPromptTemplate.from_messages([
            ("system", MINDMAP_PROMPT),
            ("human", "Tạo bản đồ tư duy cho tài liệu này."),
        ])
        
        chain = prompt | llm | StrOutputParser()
        
        try:
            raw_res = chain.invoke({"context": context})
            clean_json = extract_json(raw_res)
            mindmap_data = json.loads(clean_json)

            paths = get_course_path(self.course_id)
            save_dir = paths["mindmaps"] # Lấy từ config đã sửa ở Bước 1
            os.makedirs(save_dir, exist_ok=True)
            save_path = os.path.join(save_dir, "mindmap.json")
            
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(mindmap_data, f, indent=2, ensure_ascii=False)
            
            return mindmap_data
        except Exception as e:
            logger.error(f"Lỗi tạo Mindmap: {e}")
            raise RuntimeError(f"Không thể tạo bản đồ tư duy: {e}")