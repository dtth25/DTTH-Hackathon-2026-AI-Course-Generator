"""Prompt templates for the four public generation outputs."""

BOOK_GENERATION_PROMPT = """\
BẠN LÀ CHUYÊN GIA BIÊN SOẠN SÁCH HỌC TẬP.
NHIỆM VỤ: Phân tích [CONTEXT] và xây dựng một bản SÁCH học tập hoàn chỉnh cho đối tượng "{target_audience}".
YÊU CẦU BỔ SUNG: {user_prompt}

YÊU CẦU ĐẦU RA (CHỈ XUẤT RAW JSON):
{{
  "title": "Tên sách học tập (súc tích, hấp dẫn)",
  "description": "Mô tả tổng quan cuốn sách (2-3 câu)",
  "estimated_duration": "Ví dụ: 4-6 giờ đọc/học",
  "chapters": [
    {{
      "title": "Chương X: [Tên chương]",
      "description": "Mục tiêu và nội dung chính của chương (1-2 câu)",
      "lessons": [
        {{
          "title": "Bài Y: [Tên bài học cụ thể]",
          "duration": "20-30 phút",
          "objectives": [
            "Mục tiêu học tập cụ thể 1",
            "Mục tiêu học tập cụ thể 2"
          ],
          "lecture": "Nội dung bài học 2-4 đoạn, diễn giải rõ ý từ tài liệu gốc. Không chỉ nêu outline.",
          "key_points": [
            "Ý chính cần ghi nhớ 1",
            "Ý chính cần ghi nhớ 2",
            "Ý chính cần ghi nhớ 3"
          ],
          "activity": "Hoạt động/thảo luận/bài tập ngắn để người học thực hành",
          "assessment": [
            "Câu hỏi kiểm tra nhanh 1",
            "Câu hỏi kiểm tra nhanh 2"
          ]
        }}
      ]
    }}
  ]
}}

QUY TẮC:
- Chia từ 3-6 chương.
- Mỗi chương có 2-3 bài học nhỏ.
- Mỗi bài học PHẢI có nội dung trong trường "lecture", không được chỉ trả về title.
- Nội dung phải bám sát dữ liệu trong [CONTEXT], không thêm kiến thức ngoài tài liệu.
- Không đưa page, source hoặc chunk_id vào JSON output.
- Nội dung logic từ cơ bản đến nâng cao dựa trên tài liệu.

[CONTEXT]:
{context}
"""

QUIZ_V2_PROMPT = r"""
BẠN LÀ CHUYÊN GIA GIÁO DỤC ĐA LĨNH VỰC VÀ BIÊN SOẠN ĐỀ THI.
NHIỆM VỤ: Tạo {quantity} câu hỏi trắc nghiệm (MCQ) về "{topic}" với độ khó "{difficulty}".

QUY TẮC NỘI DUNG (KHÔNG ĐƯỢC VI PHẠM):
1. ĐÁP ÁN ĐỘC LẬP: Chỉ duy nhất một đáp án đúng. Các phương án nhiễu phải hợp lý nhưng SAI hoàn toàn.
2. CHI TIẾT: Phần giải thích (explanation) phải nêu rõ tại sao chọn đáp án đó dựa trên tài liệu.
3. LATEX: Sử dụng dấu $ cho ký hiệu toán học (ví dụ: $x$, $\in$).
4. Không đưa page, source hoặc chunk_id vào JSON output.

YÊU CẦU ĐỊNH DẠNG (CHỈ XUẤT RAW JSON ARRAY):
[
  {{
    "question": "Câu hỏi cụ thể, rõ ràng",
    "options": ["Lựa chọn 0", "Lựa chọn 1", "Lựa chọn 2", "Lựa chọn 3"],
    "correct": 0,
    "explanation": "Giải thích chi tiết vì sao chọn đáp án đó..."
  }}
]

[CONTEXT]:
{context}
"""

SLIDE_GENERATION_PROMPT = """\
BẠN LÀ CHUYÊN GIA SƯ PHẠM VÀ THIẾT KẾ TRÌNH CHIẾU CẤP CAO.
NHIỆM VỤ: Thiết kế nội dung cho {num_slides} trang slide về chủ đề "{topic}" từ [CONTEXT].

QUY TẮC TOÀN VẸN NỘI DUNG:
1. KHÔNG CẮT XÉN: Phải đi qua đầy đủ các phần của chủ đề được yêu cầu.
2. MỖI SLIDE MỘT Ý TƯỞNG: Mỗi slide chỉ chứa một khối nội dung hoặc một định nghĩa/ví dụ.
3. CẤU TRÚC SƯ PHẠM: Giới thiệu -> Nội dung chi tiết -> Ví dụ -> Kết luận.
4. Không đưa page, source hoặc chunk_id vào JSON output.

YÊU CẦU ĐỊNH DẠNG (CHỈ XUẤT RAW JSON ARRAY):
[
  {{
    "title": "Tiêu đề Slide",
    "content": "Nội dung chính (dùng Markdown gạch đầu dòng, tối đa 4-5 dòng)",
    "layout_hint": "title-and-content",
    "image_suggestion": "Mô tả hình ảnh hoặc sơ đồ minh họa phù hợp"
  }}
]

[CONTEXT]:
{context}
"""

VID_SCENES_PROMPT = """\
BẠN LÀ BIÊN TẬP VIÊN VIDEO GIÁO DỤC.
NHIỆM VỤ: Tạo kịch bản cho một video học tập dạng slide + voiceover về chủ đề "{topic}".
Video mục tiêu dài khoảng {duration_minutes} phút.

YÊU CẦU:
- Chỉ dùng kiến thức có trong [CONTEXT].
- Tạo {scene_count} cảnh.
- Mỗi cảnh có tiêu đề ngắn, chữ hiển thị trên slide, và lời voiceover tiếng Việt.
- Voiceover phải tự nhiên, dễ nghe, phù hợp video học tập.
- Không đưa page, source hoặc chunk_id vào JSON output.

YÊU CẦU ĐỊNH DẠNG (CHỈ XUẤT RAW JSON ARRAY):
[
  {{
    "title": "Tiêu đề cảnh",
    "visual_text": "3-5 gạch đầu dòng ngắn để hiển thị trên video",
    "voiceover": "Lời đọc tiếng Việt cho cảnh này"
  }}
]

[CONTEXT]:
{context}
"""
