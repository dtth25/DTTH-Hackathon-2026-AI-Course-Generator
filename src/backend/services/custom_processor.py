import logging
import os
import re
import json
from datetime import datetime
from typing import Any, Dict, List

from backend.core.config import get_llm, format_docs
from backend.core.prompts import (
    CUSTOM_INSTRUCTION_CORE,
    PROMPT_FORMAT_MAP,
    PROMPT_TEMPERATURE_MAP,
    FEW_SHOT_EXAMPLES,
)
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

logger = logging.getLogger(__name__)


def classify_prompt(user_prompt: str) -> Dict[str, Any]:
    """
    Phân loại prompt đầu vào thành 5 nhóm:
    - TABLE:   so sánh, đối chiếu, thống kê, bảng
    - LIST:    danh sách, liệt kê, các bước, quy trình
    - EXPLAIN: giải thích, phân tích, trình bày (default)
    - JSON:    json, cấu trúc dữ liệu, machine-readable
    - CODE:    code, ví dụ code, implementation
    """
    prompt_lower = user_prompt.lower()

    # Priority-based classification
    patterns = {
        "TABLE": [
            r"\bbảng\b", r"\bso\s?sánh\b", r"\bđối\s?chiếu\b",
            r"\bthống\s?kê\b", r"\btổng\s?hợp\b",
        ],
        "JSON": [
            r"\bjson\b", r"\bcấu\s?trúc\s?dữ\s?liệu\b",
            r"\bmachine.re*", r"\bparse\b",
        ],
        "CODE": [
            r"\bcode\b", r"\bví\s?dụ\s?code\b", r"\bimplementation\b",
            r"\bchạy\s?thử\b", r"\bexample\s?code\b",
        ],
        "LIST": [
            r"\bdanh\s?sách\b", r"\bliệt\s?kê\b", r"\bcác\s?bước\b",
            r"\bquy\s?trình\b", r"\bcác\s?ý\s?chính\b",
        ],
    }

    for prompt_type, regex_list in patterns.items():
        for pattern in regex_list:
            if re.search(pattern, prompt_lower):
                return {
                    "type": prompt_type,
                    "format_instruction": PROMPT_FORMAT_MAP[prompt_type],
                    "temperature": PROMPT_TEMPERATURE_MAP[prompt_type],
                }

    # Default: EXPLAIN
    return {
        "type": "EXPLAIN",
        "format_instruction": PROMPT_FORMAT_MAP["EXPLAIN"],
        "temperature": PROMPT_TEMPERATURE_MAP["EXPLAIN"],
    }


def extract_citations(docs: List[Any]) -> List[Dict[str, Any]]:
    """
    Trích xuất citations từ danh sách document chunks.
    Mỗi doc cần có metadata chứa page, source, chunk_id.
    """
    citations = []
    seen_chunks = set()

    for doc in docs:
        meta = getattr(doc, "metadata", {})
        if not meta:
            continue

        chunk_id = meta.get("chunk_id", "")
        if chunk_id in seen_chunks:
            continue
        seen_chunks.add(chunk_id)

        citation = {
            "page": meta.get("page", 0),
            "source": meta.get("source", ""),
            "chunk_id": chunk_id,
        }
        citations.append(citation)

    return citations


class CustomProcessor:
    """
    Xử lý prompt tùy chỉnh với modular prompt engineering.
    
    Architecture (3 layers):
    1. CUSTOM_INSTRUCTION_CORE: System prompt cốt định (chống ảo giác, ngôn ngữ, độ dài)
    2. Format Instruction: Tự động chọn dựa trên classify_prompt() (TABLE/LIST/EXPLAIN/JSON/CODE)
    3. Few-shot Examples: 4 ví dụ mẫu cho từng loại
    """

    def __init__(self, rag_chains):
        self.rag = rag_chains
        self.vectorstore = rag_chains.vectorstore
        self.course_id = rag_chains.course_id
        self.save_dir = os.path.join("custom_prompts", f"course_{self.course_id}")

    def process(self, user_prompt: str) -> Dict[str, Any]:
        """
        Xử lý prompt tùy chỉnh và trả về structured response kèm citations.
        
        Args:
            user_prompt: Yêu cầu của người dùng (1-2000 ký tự)
            
        Returns:
            {
                "result": str (nội dung AI trả lời),
                "prompt_type": str (TABLE/LIST/EXPLAIN/JSON/CODE),
                "citations": [{"page": int, "source": str, "chunk_id": str}, ...]
            }
        """
        self.rag._require_ready()

        # ---- Bước 1: Phân loại prompt ----
        classification = classify_prompt(user_prompt)
        prompt_type = classification["type"]
        format_instruction = classification["format_instruction"]
        temperature = classification["temperature"]

        # ---- Bước 2: Retrieve documents + extract citations ----
        retriever = self.vectorstore.as_retriever(search_kwargs={"k": 15})
        docs = retriever.invoke(user_prompt)
        context = format_docs(docs)
        citations = extract_citations(docs)

        logger.info(
            f"Custom prompt classified as '{prompt_type}' "
            f"(temp={temperature}), retrieved {len(docs)} chunks, "
            f"{len(citations)} unique citations"
        )

        # ---- Bước 3: Build full prompt (Core + Format + Few-shot + Context + User) ----
        system_message = (
            CUSTOM_INSTRUCTION_CORE
            + "\n\n"
            + format_instruction
            + "\n\n"
            + FEW_SHOT_EXAMPLES
        )

        prompt_template = ChatPromptTemplate.from_messages([
            ("system", system_message),
            ("human", "{user_prompt}"),
        ])

        llm = get_llm(temperature=temperature)
        chain = prompt_template | llm | StrOutputParser()

        # ---- Bước 4: Gọi LLM ----
        try:
            result = chain.invoke({
                "context": context,
                "user_prompt": user_prompt,
            })

            response = {
                "result": result.strip(),
                "prompt_type": prompt_type,
                "citations": citations,
            }

            # ---- Bước 5: Save kết quả vào file ----
            self._save_result(user_prompt, response)

            return response
        except Exception as e:
            logger.error(f"Lỗi xử lý prompt tùy chỉnh: {e}")
            raise RuntimeError(f"Không thể xử lý yêu cầu: {e}")

    def _save_result(self, user_prompt: str, response: Dict[str, Any]):
        """Lưu kết quả vào custom_prompts/course_{id}/{timestamp}.json và .md"""
        try:
            os.makedirs(self.save_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_path = os.path.join(self.save_dir, f"{timestamp}")

            # 1. Lưu JSON gốc (để programmatic đọc)
            payload = {
                "course_id": self.course_id,
                "prompt": user_prompt,
                "prompt_type": response["prompt_type"],
                "result": response["result"],
                "citations": response["citations"],
                "created_at": datetime.now().isoformat(),
            }
            with open(f"{base_path}.json", "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)

            # 2. Lưu Markdown người đọc được (xuống dòng thật, không escape \n)
            md_content = f"""\
# Custom Prompt Result

- **Course ID**: {self.course_id}
- **Prompt type**: `{response['prompt_type']}`
- **Prompt**: {user_prompt}
- **Created at**: {datetime.now().isoformat()}

## Result

{response['result']}

## Citations

"""
            for i, c in enumerate(response["citations"], 1):
                md_content += f"- [{i}] Page {c.get('page', '?')} — `{c.get('source', '')}` (chunk: `{c.get('chunk_id', '')}`)\n"

            with open(f"{base_path}.md", "w", encoding="utf-8") as f:
                f.write(md_content)

            logger.info(f"Đã lưu kết quả custom prompt: {base_path}.json + .md")
        except Exception as e:
            logger.warning(f"Không thể lưu kết quả custom prompt: {e}")
