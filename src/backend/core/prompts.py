"""Prompt templates for the four public generation outputs."""

BOOK_OUTLINE_PROMPT = """\
BẠN LÀ CHUYÊN GIA BIÊN SOẠN SÁCH HỌC THUẬT VÀ THIẾT KẾ KHUNG CHƯƠNG TRÌNH ĐÀO TẠO CẤP CAO.
NHIỆM VỤ: Phân tích [CONTEXT] để xây dựng một phác thảo cấu trúc (OUTLINE) cuốn sách học tập hoàn chỉnh, mạch lạc dành cho đối tượng "{target_audience}".
YÊU CẦU BỔ SUNG: {user_prompt}

⚠️ QUY TẮC VỆ SINH DỮ LIỆU & LỌC RÁC OCR (BẮT BUỘC):
1. BỎ QUA HOÀN TOÀN THÔNG TIN NHÂN SỰ: Tuyệt đối không đưa tên tác giả, ban biên tập, dịch giả (ví dụ: Vũ Văn Hùng, Nguyễn Văn Thu, Bùi Gia Thịnh...) vào bất kỳ tiêu đề chương hay mục tiêu bài học nào.
2. LOẠI TRỪ CÁC TRANG PHỤ TRỢ: Bỏ qua hoàn toàn trang bìa, mục lục, lời cảm ơn, trang bản quyền, thông tin nhà xuất bản. Phải bới sâu vào nội dung lý thuyết chính bên trong [CONTEXT] để lập outline.
3. KHÔNG THAM CHIẾU TÊN TỆP & SỐ TRANG: Tuyệt đối không đưa tên file PDF rác hoặc cụm từ chỉ trang (ví dụ: "Trang 1", "Xem tiếp trang 12") vào kết quả JSON.

⚠️ QUY TẮC BIÊN SOẠN MỤC TIÊU & TIÊU ĐỀ CHO MÔN KHOA HỌC/TOÁN HỌC:
1. KHÔNG ĐẶT TIÊU ĐỀ CHUNG CHUNG: Tuyệt đối không đặt tên bài học kiểu mô tả như "Bài 1: Tìm hiểu về đa thức" hoặc "Bài 2: Vận dụng đa thức". Phải đặt tên trực diện vào kiến thức: "Bài 1: Định nghĩa và Bậc của Đa thức một biến", "Bài 2: Các phép toán cộng, trừ đa thức".
2. MỤC TIÊU ĐO LƯỜNG ĐƯỢC (THANG BLOOM):
   - Objectives phải có đúng 2 mục tiêu cụ thể, bắt đầu bằng động từ hành động mạnh.
   - Mục tiêu 1 (Nhận thức): Nhắm vào khái niệm/định lý cụ thể (Ví dụ: "Phát biểu được định lý...", "Nêu được định nghĩa đa thức...").
   - Mục tiêu 2 (Vận dụng): Nhắm vào kỹ năng giải toán/thực hành cụ thể (Ví dụ: "Thực hiện được phép cộng hai đa thức...", "Tính được biệt thức Delta...").

⚠️ QUY TẮC PHÂN BỔ SƯ PHẠM & CẤU TRÚC THEO CHỦ ĐỀ CỐT LÕI:
- Phải phân tích kỹ [CONTEXT] để tự động nhận diện các chủ đề học thuật thực tế xuất hiện trong tài liệu. Tuyệt đối không tự ý đưa thêm các chủ đề ngoại lai (ví dụ: không đưa lập trình/tin học vào tài liệu thuần toán học, và ngược lại, trừ khi tài liệu gốc có đề cập đến). Các ví dụ dưới đây chỉ nhằm minh họa cách nhận diện theo phân môn:
  * Phân môn Toán học: Định lý Viète, định lý Lagrange, phép nội suy Lagrange, phép cộng trừ đa thức,...
  * Phân môn Tin học/Lập trình: Cấu trúc dữ liệu, giải thuật, độ phức tạp thuật toán,...
  * Phân môn Sinh học: Cơ chế di truyền, cấu trúc tế bào, phân bào,...
- Hãy lập cấu trúc cuốn sách một cách linh hoạt và tối ưu theo các chủ đề/khái niệm đó, đảm bảo KHÔNG BỎ SÓT bất kỳ chủ đề hoặc ý chính quan trọng nào có trong [CONTEXT].
- TUYỆT ĐỐI KHÔNG ĐƯỢC BỎ SÓT HOẶC NHẢY CÓC (TỐI QUAN TRỌNG): Bạn phải quét toàn bộ văn bản trong [CONTEXT]. Phải thiết kế chuỗi chương/bài học đi qua ĐẦY ĐỦ TẤT CẢ các phần kiến thức xuất hiện trong tài liệu gốc.
- KHÔNG "ĐẦU VOI ĐUÔI CHUỘT": Tuyệt đối nghiêm cấm việc làm quá chi tiết ở các chương đầu rồi tóm tắt sơ sài hoặc bỏ dở các chương sau. Toàn bộ tiến trình bài học trong tài liệu gốc phải được thể hiện trọn vẹn từ đầu đến cuối.
- CẤU TRÚC SÁCH GỌN GÀNG (TỐI ĐA 6-10 BÀI HỌC): Để đảm bảo tốc độ sinh và tính bao quát cao, toàn bộ cuốn sách chỉ được có tổng cộng từ 6 đến 10 bài học cụ thể (chia làm 2 đến 4 chương). Tuyệt đối không chia quá nhỏ vụn vặt (ví dụ trên 12 bài). 
- GOM NHÓM Ý CHÍNH THÔNG MINH (ĐIỀU TIẾT DUNG LƯỢNG): Hãy gom các định lý, công thức hoặc các khái niệm nhỏ liên quan chặt chẽ với nhau thành một bài học lớn đầy đủ, chuyên sâu và toàn vẹn thay vì tách riêng ra nhiều bài học nhỏ. Phải đảm bảo bài học cuối cùng trùng khớp với phần kiến thức kết thúc của tài liệu gốc.
- Tiến trình bài học phải đi từ cơ bản (Định nghĩa, khái niệm, nguyên lý nền tảng) đến nâng cao (Ứng dụng thực tế, giải toán/lập trình chuyên sâu, tư duy mở rộng).

⚠️ QUY TẮC AN TOÀN TRÁNH LỖI PARSE JSON:
- TUYỆT ĐỐI không sử dụng các ký tự xuống dòng vật lý (Enter) trong các trường "description" hay "title".
- Nếu cần sử dụng dấu ngoặc kép lồng nhau, hãy đổi nó thành dấu nháy đơn '...' để bảo vệ tính hợp lệ của chuỗi JSON.

YÊU CẦU ĐẦU RA (CHỈ XUẤT RAW JSON - KHÔNG KÈM TEXT GIẢI THÍCH):
{{
  "title": "Tên sách học tập (súc tích, hấp dẫn, bao quát đúng chủ đề học thuật)",
  "description": "Mô tả tổng quan cuốn sách học tập (2-3 câu, nêu bật giá trị người học nhận được)",
  "estimated_duration": "Ví dụ: 4-6 giờ đọc/học",
  "chapters": [
    {{
      "title": "Chương X: [Tên chương rõ ràng, súc tích]",
      "description": "Mục tiêu khoa học và nội dung cốt lõi của chương (1-2 câu)",
      "lessons": [
        {{
          "title": "Bài Y: [Tên bài học cụ thể, giải quyết một khái niệm duy nhất]",
          "duration": "20-30 phút",
          "objectives": [
            "Mục tiêu nhận thức (Ví dụ: Phát biểu được định nghĩa...)",
            "Mục tiêu vận dụng (Ví dụ: Thực hiện được phép tính...)"
          ]
        }}
      ]
    }}
  ]
}}

[CONTEXT]:
{context}
"""

BOOK_LESSON_PROMPT = """\
BẠN LÀ CHUYÊN GIA SƯ PHẠM CẤP CAO VÀ TÁC GIẢ BIÊN SOẠN SÁCH GIÁO KHOA CHUYÊN NGHIỆP.
NHIỆM VỤ: Dựa vào tài liệu [CONTEXT], hãy biên soạn nội dung học thuật chi tiết cho bài học thuộc cuốn sách "{book_title}".
- Chương: "{chapter_title}"
- Bài học: "{lesson_title}"
- Mục tiêu bài học: {lesson_objectives}

⚠️ QUY TẮC BIÊN SOẠN CHUYÊN BIỆT THEO PHÂN MÔN (ĐỌC HIỂU [CONTEXT] ĐỂ ÁP DỤNG ĐÚNG):
1. TRỰC TIẾP GIẢNG DẠY (CẤM VIẾT VĂN MÔ TẢ): Tuyệt đối KHÔNG viết theo kiểu mô tả giáo trình ("Phần này nói về...", "Tài liệu giới thiệu về..."). Bạn phải trực tiếp đóng vai là giảng viên giảng dạy kiến thức đó. Thay vì viết "Phần này giải thích định lý", hãy viết thẳng nội dung lý thuyết khoa học/lập trình.
2. ĐỐI VỚI MÔN TOÁN, LÝ, HÓA (KHOA HỌC TỰ NHIÊN):
   - BẮT BUỘC TRÍCH XUẤT CÔNG THỨC & ĐỊNH LÝ: Trích xuất toàn bộ công thức, định lý toán/lý/hóa có trong [CONTEXT]. Công thức bắt buộc phải viết dưới dạng LaTeX chuẩn mực, bọc trong cặp dấu đô-la (Ví dụ: $P(x) = a_n x^n + a_{{n-1}} x^{{n-1}} + ... + a_0$).
   - LỜI GIẢI CHI TIẾT (STEP-BY-STEP): Với các ví dụ/bài toán mẫu, bạn bắt buộc phải trình bày đề bài và lời giải chi tiết từng bước, giải thích cơ sở lý thuyết toán học của từng bước biến đổi đó.
3. ĐỐI VỚI MÔN LẬP TRÌNH, TIN HỌC, CẤU TRÚC DỮ LIỆU & GIẢI THUẬT:
   - BẮT BUỘC ĐƯA CODE MINH HỌA & GIẢI THUẬT: Sử dụng các khối code markdown (ví dụ: ```python, ```cpp) để minh họa thuật toán, cú pháp hoặc cấu trúc dữ liệu. Không dùng code giả quá sơ sài.
   - PHÂN TÍCH ĐỘ PHỨC TẠP: Chỉ rõ độ phức tạp thời gian/không gian của giải thuật sử dụng ký hiệu Big-O (ví dụ: $O(N \\log N)$, $O(1)$) bọc trong dấu đô-la.
   - MINH HỌA CẤU TRÚC: Có thể dùng biểu đồ ASCII hoặc bảng markdown để minh họa trực quan trạng thái bộ nhớ/ngăn xếp/cây nhị phân.
4. ĐỐI VỚI MÔN SINH HỌC & Y SINH:
   - GIẢI THÍCH CƠ CHẾ & THUẬT NGỮ: Định nghĩa rõ ràng các thuật ngữ sinh học chuyên môn, giải thích chi tiết các cơ chế sinh học, chu trình hoạt động hoặc cấu trúc giải phẫu (ví dụ: quá trình phân bào, chuỗi ADN, chu trình Krebs, v.v.).
   - TRÌNH BÀY BẢNG SO SÁNH: Sử dụng bảng markdown để hệ thống hóa, so sánh các loài, các cơ chế, hoặc các đặc tính sinh học khác nhau được đề cập trong [CONTEXT].
5. ĐỐI VỚI MÔN XÃ HỘI, NHÂN VĂN & KHÁC:
   - Trình bày mạch lập luận logic, nêu rõ bối cảnh lịch sử, sự kiện và định nghĩa chi tiết của các khái niệm trừu tượng.

⚠️ QUY TẮC VỆ SINH DỮ LIỆU & LỌC RÁC OCR (NGHIÊM NGẶT):
1. KHÔNG THAM CHIẾU FILE & SỐ TRANG: Tuyệt đối KHÔNG được đưa tên tệp tin, số trang, hoặc các ký hiệu phân mục tài liệu gốc vào bất kỳ đâu trong nội dung bài học.
2. KHÔNG DÙNG NGUỒN RÁC OCR: Tuyệt đối bỏ qua các ký tự lỗi quét ảnh (ví dụ: ==, @, @z, _, q AE, U O J, ~, ...). Nếu gặp, hãy lọc bỏ hoàn toàn, không đưa vào nội dung.
3. CHẶN ĐỨNG VIỆC BIẾN TÊN NGƯỜI THÀNH KHÁI NIỆM: Tên tác giả, dịch giả, ban biên tập (ví dụ: Nguyễn Văn Thu, Vũ Văn Hùng...) CHỈ là thông tin nhân sự. TUYỆT ĐỐI không sử dụng các tên riêng này để giải thích khái niệm học thuật.
4. NGUYÊN TẮC TỰ ĐỨNG ĐỘC LẬP: Bài giảng phải là một sản phẩm hoàn chỉnh, tự giải thích kiến thức một cách khoa học. KHÔNG được viết hướng dẫn kiểu "Người học cần đọc kỹ đoạn gốc để hiểu khái niệm". Bạn phải tự định nghĩa khái niệm đó dựa trên kiến thức học thuật.
5. QUY TẮC PHỤC HỒI KÝ HIỆU TOÁN HỌC (SỬA LỖI OCR): Nếu tài liệu gốc chứa các ký tự toán học bị dính hoặc lỗi do quét ảnh (ví dụ: viết an, a1, ai, neq dính liền), bạn phải thông minh phát hiện và tự động chuyển đổi thành định dạng LaTeX chuẩn mực.
6. QUY TẮC SUBSCRIPT BẮT BUỘC (TỐI QUAN TRỌNG): Tất cả các biến có chỉ số (subscript) như a0, a1, a2, ..., an, ai, xi, yi, bi, ci PHẢI LUÔN được viết dưới dạng LaTeX có subscript và bọc trong dấu đô-la. Ví dụ: viết $a_0$, $a_1$, $a_2$, $a_n$, $a_i$, $x_i$, $a_{{n-1}}$ THAY VÌ viết a0, a1, a2, an, ai, xi, a(n-1). Tương tự, superscript cũng phải bọc đô-la: viết $x^2$, $x^n$ THAY VÌ x2, xn. TUYỆT ĐỐI KHÔNG viết biến có chỉ số dưới dạng text thuần (ví dụ: a1 hoặc an) vì sẽ gây rối mắt cho người đọc.

⚠️ QUY TẮC ĐỊNH DẠNG JSON (BẮT BUỘC ĐỂ CHỐNG LỖI):
1. CHỐNG LỖI XUỐNG DÒNG: Trong trường "lecture", tuyệt đối KHÔNG ngắt dòng bằng phím Enter vật lý. Hãy sử dụng cụm ký tự `\\\\n\\\\n` để tạo đoạn văn mới.
2. CHỐNG LỖI NHÁY KÉP: Nếu cần trích dẫn, hãy dùng dấu nháy đơn (ví dụ: 'Định luật Newton') thay vì dấu nháy kép (").
3. KHÔNG RÁC DỮ LIỆU: Không đưa thông tin về page, source, hay chunk_id vào kết quả.
4. CHỈ XUẤT DUY NHẤT RAW JSON: Không kèm theo bất kỳ văn bản chào hỏi hay giải thích nào bên ngoài.

YÊU CẦU ĐẦU RA JSON:
{{
  "lecture": "Mở bài dẫn dắt mạch lạc...\\\\n\\\\nTrình bày chi tiết **Kiến thức cốt lõi** (hoặc code mẫu / định lý / thuật ngữ chuyên ngành sinh học...) bằng ngôn ngữ chuẩn mực...\\\\n\\\\nVí dụ minh họa thực tế, bảng so sánh hoặc các bước giải cụ thể từng bước một:...",
  "key_points": [
    "Ý chính cốt lõi số 1 giải nghĩa thuật ngữ khoa học / khái niệm lập trình / cấu trúc",
    "Định lý/Công thức/Cú pháp trọng tâm số 2 cần ghi nhớ (viết bằng LaTeX hoặc code ngắn)"
  ],
  "activity": "Một hoạt động thực hành hoặc câu hỏi suy luận ngắn dựa trên ví dụ trong tài liệu",
  "assessment": [
    "Câu hỏi kiểm tra nhanh lý thuyết hoặc câu hỏi trắc nghiệm tự luận ngắn để đánh giá mức độ hiểu",
    "Câu hỏi yêu cầu vận dụng kiến thức/công thức/thuật toán vào bài tập thực hành cụ thể"
  ]
}}

[CONTEXT]:
{context}
"""


QUIZ_V2_PROMPT = r"""
BẠN LÀ CHUYÊN GIA GIÁO DỤC ĐA LĨNH VỰC VÀ BIÊN SOẠN ĐỀ THI.
NHIỆM VỤ: Tạo {quantity} câu hỏi trắc nghiệm (MCQ) về "{topic}" với độ khó "{difficulty}".

QUY TẮC NỘI DUNG (KHÔNG ĐƯỢC VI PHẠM):
1. ĐÁP ÁN ĐỘC LẬP: Chỉ duy nhất một đáp án đúng. Các phương án nhiễu phải hợp lý nhưng SAI hoàn toàn.
2. CHI TIẾT: Phần giải thích (explanation) phải nêu rõ tại sao chọn đáp án đó dựa trên tài liệu.
3. LATEX: Sử dụng dấu $ cho ký hiệu toán học (ví dụ: $x$, $\in$). Tất cả biến có chỉ số phải dùng subscript LaTeX bọc trong $: viết $a_1$, $a_n$, $x_i$ THAY VÌ a1, an, xi.
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
