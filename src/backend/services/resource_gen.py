"""
Resource generation service: Quiz, Flashcard, Slide, Summary, Podcast, Study Guide.
Mapping: Features 6.4-6.9 [11, 13, 14]
"""
import os
import json
import time
import re
import shutil
import logging
from typing import List, Optional, Tuple, Dict, Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from backend.core.config import (
    get_llm,
    format_docs,
    extract_json,
    sanitize_filename,
    get_course_path,
    QUESTIONS_DIR,
    AUDIO_DIR,
    GUIDES_DIR,
    FLASHCARDS_DIR,
    logger,
)
from backend.core.prompts import (
    COURSE_GENERATION_PROMPT,
    QUIZ_V2_PROMPT,
    SLIDES_V2_PROMPT,
    SUMMARY_V2_PROMPT, 
    FLASHCARDS_V2_PROMPT, 
    PODCAST_SCRIPT_PROMPT,
    STUDY_GUIDE_PROMPT,
    CONTINUE_GUIDE_PROMPT,
)


class ResourceGenerator:
    """
    Generates learning resources (Quiz, Flashcard, Slide, Summary, Podcast, Study Guide)
    from an initialized RAGChains instance.
    """

    def __init__(self, rag_chains):
        """
        Args:
            rag_chains: An initialized RAGChains instance with vectorstore.
        """
        self.rag = rag_chains
        self.course_id = rag_chains.course_id
        self.vectorstore = rag_chains.vectorstore
        
    def _get_citations(self, docs):
        """Tạo danh sách trích dẫn từ Metadata của tài liệu."""
        return [
            {
                "page": d.metadata.get("page", 1),
                "source": os.path.basename(d.metadata.get("source", "unknown.pdf")),
                "chunk_id": f"chunk_{hash(d.page_content) % 1000}"
            } for d in docs[:3]
        ]
        
    def generate_course_structure(self, user_prompt: str, target_audience: str):
        retriever = self.vectorstore.as_retriever(search_kwargs={"k": 10})
        docs = retriever.invoke(user_prompt or "tổng quan")
        prompt = ChatPromptTemplate.from_template(COURSE_GENERATION_PROMPT)
        chain = prompt | get_llm(temperature=0.3) | StrOutputParser()
        res = chain.invoke({
            "context": format_docs(docs),
            "user_prompt": user_prompt or "Không có",
            "target_audience": target_audience or "người học chung"
        })
        return {"course": json.loads(extract_json(res)), "citations": self._get_citations(docs)}

    # 4.2 Summary
    def generate_summary_v2(self, summary_type: str = "detailed"):
        retriever = self.vectorstore.as_retriever(search_kwargs={"k": 15})
        docs = retriever.invoke("nội dung trọng tâm")
        instructions = {
            "short": "Viết 1 đoạn văn 70 từ.",
            "detailed": "Phân tích sâu, chia mục rõ ràng.",
            "key_points": "Chỉ liệt kê các gạch đầu dòng cốt lõi.",
            "conclusion": "Tập trung vào giá trị cuối cùng."
        }
        prompt = ChatPromptTemplate.from_template(SUMMARY_V2_PROMPT)
        chain = prompt | get_llm(temperature=0.2) | StrOutputParser()
        res = chain.invoke({
            "context": format_docs(docs),
            "type": summary_type
        })
        return {"summary": res, "citations": self._get_citations(docs)}

    # 4.3 Flashcards
    def generate_flashcards_v2(self, count: int):
        retriever = self.vectorstore.as_retriever(search_kwargs={"k": 15})
        docs = retriever.invoke("khái niệm định nghĩa")
        prompt = ChatPromptTemplate.from_template(FLASHCARDS_V2_PROMPT)
        chain = prompt | get_llm(temperature=0.3) | StrOutputParser()
        res = chain.invoke({"context": format_docs(docs), "count": count})
        return {"flashcards": json.loads(extract_json(res)), "citations": self._get_citations(docs)}

    # 4.4 Quiz
    def generate_quiz_v2(self, topic: str, quantity: int, difficulty: str):
        retriever = self.vectorstore.as_retriever(search_kwargs={"k": 15})
        docs = retriever.invoke(topic)
        prompt = ChatPromptTemplate.from_template(QUIZ_V2_PROMPT)
        chain = prompt | get_llm(temperature=0.3) | StrOutputParser()
        res = chain.invoke({
            "context": format_docs(docs), "topic": topic, 
            "quantity": quantity, "difficulty": difficulty
        })
        return {"questions": json.loads(extract_json(res)), "citations": self._get_citations(docs)}

    # 4.5 Slides
    def generate_slides_v2(self, topic: str, num_slides: int):
        retriever = self.vectorstore.as_retriever(search_kwargs={"k": 15})
        docs = retriever.invoke(topic)
        prompt = ChatPromptTemplate.from_template(SLIDES_V2_PROMPT)
        chain = prompt | get_llm(temperature=0.1) | StrOutputParser()
        res = chain.invoke({
            "context": format_docs(docs), "topic": topic, "num_slides": num_slides
        })
        return {"slides": json.loads(extract_json(res)), "citations": self._get_citations(docs)}
        
    

    

    # ═══════════════════════════════════════════════════════════════════════════
    # PODCAST — Feature 6.7 [14]
    # ═══════════════════════════════════════════════════════════════════════════
    
    

    def generate_podcast_script(self) -> list:
        """Generate podcast dialogue script."""
        self.rag._require_ready()
        try:
            logger.info(" -> Đang tạo kịch bản podcast (LLM)...")
            raw = self.rag.audio_chain.invoke({})
            clean = extract_json(raw)
            data = json.loads(clean, strict=False)

            script = []
            if isinstance(data, list):
                script = data
            elif isinstance(data, dict):
                for key in ["podcast", "script", "segments", "dialogue"]:
                    if key in data and isinstance(data[key], list):
                        script = data[key]
                        break
                if not script:
                    for val in data.values():
                        if isinstance(val, list):
                            script = val
                            break

            if not script:
                raise ValueError("Không tìm thấy mảng hội thoại trong JSON trả về.")

            audio_dir = get_course_path(self.course_id)["audio"]
            os.makedirs(audio_dir, exist_ok=True)
            script_path = os.path.join(audio_dir, "podcast_script.json")

            with open(script_path, "w", encoding="utf-8") as f:
                json.dump(script, f, indent=2, ensure_ascii=False)

            return script
        except Exception as e:
            logger.error(f"[PodcastScript] LỖI: {e}")
            raise

    def generate_podcast_audio(self) -> str:
        """Chuyển kịch bản thành MP3 - Bản sửa lỗi lọc ký tự đặc biệt và xử lý file rỗng."""
        import edge_tts
        import asyncio
        import shutil
        import threading
        import re
        from pydub import AudioSegment

        # Ép đường dẫn FFmpeg cho Mac
        possible_ffmpeg = ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "ffmpeg"]
        for path in possible_ffmpeg:
            if shutil.which(path):
                AudioSegment.converter = path
                break

        def clean_text_for_tts(text: str) -> str:
            """Loại bỏ các ký tự LaTeX và ký tự đặc biệt gây lỗi TTS."""
            # Xóa các ký hiệu toán học $...$
            text = re.sub(r'\$.*?\$', '', text)
            # Xóa các ký tự backslash và lệnh LaTeX
            text = text.replace('\\', ' ')
            # Chỉ giữ lại chữ cái, số, dấu câu tiếng Việt cơ bản
            text = re.sub(r'[^\w\s,.\?!\-áàảãạâấầẩẫậăắằẳẵặéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵĐđ]', ' ', text)
            # Xóa khoảng trắng thừa
            return re.sub(r'\s+', ' ', text).strip()

        self.rag._require_ready()
        try:
            audio_dir = get_course_path(self.course_id)["audio"]
            script_path = os.path.join(audio_dir, "podcast_script.json")
            final_audio_path = os.path.join(audio_dir, "podcast_full.mp3")

            with open(script_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)

            # --- 1. CHUẨN HÓA & LÀM SẠCH VĂN BẢN ---
            script = []
            items = raw_data if isinstance(raw_data, list) else []
            if isinstance(raw_data, dict):
                for val in raw_data.values():
                    if isinstance(val, list): items = val; break
            
            for item in items:
                if isinstance(item, dict):
                    raw_text = str(item.get("text", ""))
                    cleaned_text = clean_text_for_tts(raw_text)
                    if len(cleaned_text) > 1:
                        script.append({
                            "speaker": str(item.get("speaker", "Alice")),
                            "text": cleaned_text
                        })

            temp_dir = os.path.join(audio_dir, "temp_chunks")
            if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
            os.makedirs(temp_dir, exist_ok=True)

            # --- 2. HÀM CHẠY TTS (Có bắt lỗi từng dòng) ---
            async def tts_worker():
                voices = {"Alice": "vi-VN-HoaiMyNeural", "Bob": "vi-VN-NamMinhNeural"}
                for i, line in enumerate(script):
                    voice = voices.get(line["speaker"], voices["Alice"])
                    chunk_path = os.path.join(temp_dir, f"line_{i:03d}.mp3")
                    try:
                        comm = edge_tts.Communicate(line["text"], voice)
                        await comm.save(chunk_path)
                    except Exception as e:
                        logger.error(f" -> Bỏ qua dòng {i+1} do lỗi TTS: {e}")
                        # Không tạo file rỗng, để tí nữa logic merge sẽ tự bỏ qua

            def start_loop():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                new_loop.run_until_complete(tts_worker())
                new_loop.close()

            logger.info(" -> Đang chuyển văn bản thành giọng nói...")
            thread = threading.Thread(target=start_loop)
            thread.start()
            thread.join()

            # --- 3. GỘP FILE (Thông minh: Bỏ qua file lỗi/rỗng) ---
            logger.info(" -> Đang ráp nối các đoạn âm thanh hợp lệ...")
            combined = AudioSegment.empty()
            chunks = sorted([f for f in os.listdir(temp_dir) if f.endswith(".mp3")])
            
            valid_count = 0
            for chunk_file in chunks:
                path = os.path.join(temp_dir, chunk_file)
                # Kiểm tra file có nội dung (không phải 0 byte)
                if os.path.getsize(path) > 100: 
                    try:
                        segment = AudioSegment.from_mp3(path)
                        combined += segment
                        combined += AudioSegment.silent(duration=600)
                        valid_count += 1
                    except:
                        logger.warning(f" -> File {chunk_file} bị lỗi decode, bỏ qua.")

            if valid_count == 0:
                raise RuntimeError("Không có đoạn âm thanh nào hợp lệ để tạo Podcast.")

            combined.export(final_audio_path, format="mp3")
            shutil.rmtree(temp_dir)
            logger.info(f"✅ Podcast thành công với {valid_count} đoạn hội thoại!")
            return final_audio_path

        except Exception as e:
            logger.error(f"[PodcastAudio] LỖI: {str(e)}")
            raise RuntimeError(f"Lỗi hệ thống âm thanh: {e}")

    # ═══════════════════════════════════════════════════════════════════════════
    # STUDY GUIDE — Feature 6.8 [14]
    # ═══════════════════════════════════════════════════════════════════════════

    def generate_study_guide(self) -> str:
        """Generate structured study guide with auto-continue logic."""
        self.rag._require_ready()

        retriever = self.vectorstore.as_retriever(search_kwargs={"k": 15})
        docs = retriever.invoke("nội dung chi tiết hệ thống hóa kiến thức")
        full_context = "\n\n".join([doc.page_content for doc in docs])

        logger.info(" -> Đang tạo phần 1 của Study Guide...")
        guide_content = self.rag.guide_chain.invoke({"topic": "nội dung chi tiết"}).strip()

        max_parts = 2
        for i in range(max_parts):
            if any(marker in guide_content for marker in ["V. CÂU HỎI", "📌 V.", "TÓM TẮT BÀI HỌC"]):
                break

            logger.info(f" -> Phát hiện nội dung bị cắt cụt, đang viết tiếp phần {i+2}...")

            continue_llm = get_llm(temperature=0.2)
            continue_prompt = ChatPromptTemplate.from_messages([
                ("system", CONTINUE_GUIDE_PROMPT),
                ("human", "Hãy viết tiếp bản thảo."),
            ])
            continue_chain = continue_prompt | continue_llm | StrOutputParser()

            last_context = guide_content[-1000:]
            additional_content = continue_chain.invoke({
                "context": full_context,
                "existing_content": last_context
            }).strip()

            if guide_content[-1] in [".", "!", "?", "}", "]", "\n"]:
                guide_content += "\n\n" + additional_content
            else:
                guide_content += " " + additional_content

            time.sleep(2)

        guide_content = guide_content.replace("---", "").replace("---", "")

        guides_dir = get_course_path(self.course_id)["guides"]
        os.makedirs(guides_dir, exist_ok=True)
        guide_path = os.path.join(guides_dir, "study_guide.md")

        with open(guide_path, "w", encoding="utf-8") as f:
            f.write(guide_content)

        return guide_content

    # ═══════════════════════════════════════════════════════════════════════════
    # FLASHCARDS — Feature 6.9 [14]
    # ═══════════════════════════════════════════════════════════════════════════

    