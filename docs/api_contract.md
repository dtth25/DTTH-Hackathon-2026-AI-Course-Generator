# API Contract (v1.0)

## 1. Document Ingestion
- **POST `/api/upload`**
  - Input: `file: MultipartFile`
  - Output: `{"file_id": "uuid", "pages": 20, "status": "processed"}`

## 2. Course Generation
- **POST `/api/generate-course`**
  - Input: `{"file_id": "uuid", "user_prompt": "string"}`
  - Output: 
    ```json
    {
      "course_title": "string",
      "chapters": [
        { "id": 1, "title": "string", "lessons": ["string"] }
      ]
    }
    ```