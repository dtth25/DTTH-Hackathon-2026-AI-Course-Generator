export interface Citation {
  page: number;
  source: string;
  chunk_id: string;
}

export interface Lesson {
  id: string;
  title: string;
  content?: string;
  citations?: Citation[];
}

export interface Chapter {
  id: number;
  title: string;
  lessons: Lesson[];
}

export interface Course {
  course_title: string;
  chapters: Chapter[];
}