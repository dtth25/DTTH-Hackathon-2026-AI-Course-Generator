'use client';

import * as React from 'react';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  AppBar,
  Avatar,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Container,
  Divider,
  LinearProgress,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Paper,
  Snackbar,
  Tab,
  Tabs,
  Typography,
} from '@mui/material';
import {
  BookOpen,
  BrainCircuit,
  CheckCircle2,
  ChevronDown,
  FileUp,
  GraduationCap,
  Headphones,
  Layers3,
  Lightbulb,
  Presentation,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Target,
} from 'lucide-react';


function Stack({
  direction = 'column',
  spacing = 0,
  gap,
  alignItems,
  justifyContent,
  py,
  px,
  flexWrap,
  useFlexGap,
  sx,
  ...props
}) {
  const stackSx = {
    display: 'flex',
    flexDirection: direction,
    gap: gap !== undefined ? gap : spacing,
    ...(alignItems ? { alignItems } : {}),
    ...(justifyContent ? { justifyContent } : {}),
    ...(py !== undefined ? { py } : {}),
    ...(px !== undefined ? { px } : {}),
    ...(flexWrap ? { flexWrap } : {}),
    ...(sx || {}),
  };
  return <Box sx={stackSx} {...props} />;
}

function TabPanel({ value, index, children }) {
  if (value !== index) return null;
  return <Box sx={{ pt: 3 }}>{children}</Box>;
}

function ResponsiveGrid({ children, columns = { xs: 1, md: 2 }, gap = 2, sx = {} }) {
  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: {
          xs: `repeat(${columns.xs || 1}, minmax(0, 1fr))`,
          md: `repeat(${columns.md || 2}, minmax(0, 1fr))`,
        },
        gap,
        ...sx,
      }}
    >
      {children}
    </Box>
  );
}

function SourceBlock({ value, title }) {
  return (
    <Paper
      variant="outlined"
      sx={{
        p: 2,
        bgcolor: '#0f172a',
        color: '#e2e8f0',
        overflow: 'auto',
        maxHeight: 540,
        borderRadius: 3,
      }}
    >
      <Typography variant="overline" sx={{ color: '#93c5fd', fontWeight: 900 }}>{title}</Typography>
      <Box component="pre" sx={{ whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.65, m: 0, mt: 1 }}>
        {value || 'Chưa có nội dung nguồn.'}
      </Box>
    </Paper>
  );
}

function EmptyPreview() {
  return (
    <Card className="mono-card" sx={{ minHeight: 430 }}>
      <CardContent>
        <Stack spacing={2}>
          <Stack direction="row" alignItems="center" justifyContent="space-between">
            <Typography variant="overline" color="#93c5fd">STUDYHACK COURSE COMPILER v5.5.3</Typography>
            <Chip size="small" label="Server-side safe" color="success" />
          </Stack>
          <Typography variant="h4" sx={{ color: 'white', fontWeight: 900 }}>
            PDF → Maintainable Course Package
          </Typography>
          <Typography sx={{ color: '#cbd5e1' }}>
            Bản này không chỉ tạo quiz. Backend tạo một course package có bài giảng sâu, flashcard lật, quiz, slide Marp, slide LaTeX Beamer và quality report.
          </Typography>
          <Divider sx={{ borderColor: 'rgba(148,163,184,.25)' }} />
          {[
            '1. Client upload PDF qua Next.js server route',
            '2. FastAPI bóc tách PDF và gọi Gemini server-side',
            '3. AI tạo lesson theo cấu trúc bài giảng đại học',
            '4. Lưu ra data/courses/<course>/ để khóa sau sửa và dùng lại',
          ].map((item) => (
            <Stack key={item} direction="row" spacing={1.5} alignItems="center">
              <CheckCircle2 size={18} color="#22c55e" />
              <Typography sx={{ color: '#e2e8f0' }}>{item}</Typography>
            </Stack>
          ))}
        </Stack>
      </CardContent>
    </Card>
  );
}

function CourseHeader({ course }) {
  return (
    <Card>
      <CardContent>
        <Stack spacing={2}>
          <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" gap={2}>
            <Box>
              <Typography variant="overline" color="primary" fontWeight={900}>Khóa học AI đã biên soạn</Typography>
              <Typography variant="h4" sx={{ fontWeight: 900 }}>{course.title}</Typography>
              <Typography color="text.secondary">Nguồn: {course.source_file}</Typography>
            </Box>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              <Chip icon={<GraduationCap size={16} />} label={course.recommended_level} />
              <Chip icon={<BookOpen size={16} />} label={course.subject} color="primary" variant="outlined" />
              <Chip icon={<Target size={16} />} label={`${course.lessons?.length || 0} bài học`} color="success" variant="outlined" />
            </Stack>
          </Stack>
          <Alert severity="info">{course.summary}</Alert>
          <ResponsiveGrid columns={{ xs: 1, md: 2 }} gap={1.2}>
            {(course.course_goals || []).map((goal, idx) => (
              <Paper key={idx} variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
                <Stack direction="row" spacing={1.2} alignItems="flex-start">
                  <CheckCircle2 size={17} color="#2563eb" />
                  <Typography variant="body2">{goal}</Typography>
                </Stack>
              </Paper>
            ))}
          </ResponsiveGrid>
        </Stack>
      </CardContent>
    </Card>
  );
}

function LessonsView({ lessons, glossary, teacherNotes }) {
  return (
    <Stack spacing={2}>
      {lessons.map((lesson, index) => (
        <Accordion key={`${lesson.title}-${index}`} defaultExpanded={index === 0}>
          <AccordionSummary expandIcon={<ChevronDown />}>
            <Stack direction="row" spacing={1.5} alignItems="center">
              <Avatar sx={{ bgcolor: 'primary.main', width: 34, height: 34 }}>{index + 1}</Avatar>
              <Box>
                <Typography fontWeight={900}>{lesson.title}</Typography>
                <Typography variant="caption" color="text.secondary">{lesson.page_reference}</Typography>
              </Box>
            </Stack>
          </AccordionSummary>
          <AccordionDetails>
            <Stack spacing={2.2}>
              <ResponsiveGrid columns={{ xs: 1, md: 2 }} gap={2}>
                <Paper variant="outlined" sx={{ p: 2, borderRadius: 3 }}>
                  <Typography fontWeight={900} gutterBottom>Mục tiêu học tập</Typography>
                  <List dense>
                    {(lesson.learning_objectives || []).map((item, idx) => (
                      <ListItem key={idx} disableGutters>
                        <ListItemIcon sx={{ minWidth: 30 }}><Target size={16} /></ListItemIcon>
                        <ListItemText primary={item} />
                      </ListItem>
                    ))}
                  </List>
                </Paper>
                <Paper variant="outlined" sx={{ p: 2, borderRadius: 3 }}>
                  <Typography fontWeight={900} gutterBottom>Kiến thức cần biết trước</Typography>
                  <List dense>
                    {(lesson.prerequisites || []).map((item, idx) => (
                      <ListItem key={idx} disableGutters>
                        <ListItemIcon sx={{ minWidth: 30 }}><Lightbulb size={16} /></ListItemIcon>
                        <ListItemText primary={item} />
                      </ListItem>
                    ))}
                  </List>
                </Paper>
              </ResponsiveGrid>

              <Alert severity="success"><b>Bức tranh lớn:</b> {lesson.big_picture}</Alert>

              <Paper variant="outlined" sx={{ p: 2.5, borderRadius: 3 }}>
                <Typography variant="h6" fontWeight={900} gutterBottom>Lý thuyết cốt lõi</Typography>
                <Typography sx={{ whiteSpace: 'pre-wrap', lineHeight: 1.85 }}>{lesson.core_theory}</Typography>
              </Paper>

              <Paper variant="outlined" sx={{ p: 2.5, borderRadius: 3 }}>
                <Typography variant="h6" fontWeight={900} gutterBottom>Diễn giải / Suy luận từng bước</Typography>
                <Typography sx={{ whiteSpace: 'pre-wrap', lineHeight: 1.85 }}>{lesson.derivation_or_reasoning}</Typography>
              </Paper>

              {(lesson.worked_examples || []).map((example, idx) => (
                <Paper key={idx} variant="outlined" sx={{ p: 2.5, borderRadius: 3, bgcolor: 'rgba(37,99,235,.035)' }}>
                  <Stack spacing={1.2}>
                    <Typography fontWeight={900}>Ví dụ mẫu: {example.title}</Typography>
                    <Typography><b>Bài toán:</b> {example.problem}</Typography>
                    <List dense>
                      {(example.solution_steps || []).map((step, stepIdx) => (
                        <ListItem key={stepIdx} disableGutters>
                          <ListItemIcon sx={{ minWidth: 34 }}><Chip size="small" label={stepIdx + 1} /></ListItemIcon>
                          <ListItemText primary={step} />
                        </ListItem>
                      ))}
                    </List>
                    <Alert severity="info"><b>Kết luận:</b> {example.final_answer} <br />Nguồn: {example.page_reference}</Alert>
                  </Stack>
                </Paper>
              ))}

              <ResponsiveGrid columns={{ xs: 1, md: 2 }} gap={2}>
                <Paper variant="outlined" sx={{ p: 2, borderRadius: 3 }}>
                  <Typography fontWeight={900} gutterBottom>Lỗi thường gặp</Typography>
                  <List dense>
                    {(lesson.common_mistakes || []).map((item, idx) => (
                      <ListItem key={idx} disableGutters><ListItemText primary={`• ${item}`} /></ListItem>
                    ))}
                  </List>
                </Paper>
                <Paper variant="outlined" sx={{ p: 2, borderRadius: 3 }}>
                  <Typography fontWeight={900} gutterBottom>Checkpoint</Typography>
                  <Stack spacing={1}>
                    {(lesson.checkpoints || []).map((cp, idx) => (
                      <Alert key={idx} severity="warning">
                        <b>Hỏi:</b> {cp.question}<br />
                        <b>Đáp án kỳ vọng:</b> {cp.expected_answer}
                      </Alert>
                    ))}
                  </Stack>
                </Paper>
              </ResponsiveGrid>

              <Alert severity="success"><b>Tóm tắt:</b> {lesson.summary}</Alert>
              <Paper variant="outlined" sx={{ p: 2, borderRadius: 3 }}>
                <Typography fontWeight={900} gutterBottom>Luyện tập thêm</Typography>
                <List dense>
                  {(lesson.further_practice || []).map((item, idx) => (
                    <ListItem key={idx} disableGutters><ListItemText primary={`• ${item}`} /></ListItem>
                  ))}
                </List>
              </Paper>
            </Stack>
          </AccordionDetails>
        </Accordion>
      ))}

      <ResponsiveGrid columns={{ xs: 1, md: 2 }} gap={2}>
        <Card>
          <CardContent>
            <Typography variant="h6" fontWeight={900} gutterBottom>Glossary</Typography>
            <Stack spacing={1}>
              {(glossary || []).map((item, idx) => (
                <Paper key={idx} variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
                  <Typography fontWeight={900}>{item.term}</Typography>
                  <Typography variant="body2" color="text.secondary">{item.definition}</Typography>
                  <Typography variant="caption" color="primary">{item.page_reference}</Typography>
                </Paper>
              ))}
            </Stack>
          </CardContent>
        </Card>
        <Card>
          <CardContent>
            <Typography variant="h6" fontWeight={900} gutterBottom>Teacher Notes</Typography>
            <Typography sx={{ whiteSpace: 'pre-wrap', lineHeight: 1.8 }}>{teacherNotes}</Typography>
          </CardContent>
        </Card>
      </ResponsiveGrid>
    </Stack>
  );
}

function getStoredProgress(courseId) {
  if (typeof window === 'undefined') return {};
  try {
    return JSON.parse(localStorage.getItem(`studyhack-flashcards-${courseId}`) || '{}');
  } catch {
    return {};
  }
}

function InteractiveFlashcard({ card, index, progress, setProgress, courseId }) {
  const [flipped, setFlipped] = React.useState(false);
  const status = progress[card.id] || 'new';

  function mark(nextStatus) {
    const next = { ...progress, [card.id]: nextStatus };
    setProgress(next);
    if (typeof window !== 'undefined') {
      localStorage.setItem(`studyhack-flashcards-${courseId}`, JSON.stringify(next));
    }
  }

  const statusLabel = status === 'forgot' ? 'Chưa nhớ' : status === 'almost' ? 'Hơi nhớ' : status === 'known' ? 'Đã nhớ' : 'Mới';
  const statusColor = status === 'known' ? 'success' : status === 'forgot' ? 'error' : status === 'almost' ? 'warning' : 'default';

  return (
    <Stack spacing={1.5}>
      <Box className="flip-card" onClick={() => setFlipped((value) => !value)} role="button" tabIndex={0}>
        <Box className={`flip-card-inner ${flipped ? 'is-flipped' : ''}`}>
          <Card className="flip-card-face">
            <CardContent>
              <Stack spacing={1.5}>
                <Stack direction="row" justifyContent="space-between" alignItems="center">
                  <Chip size="small" label={`Flashcard ${index + 1}`} color="primary" />
                  <Chip size="small" label={statusLabel} color={statusColor} />
                </Stack>
                <Typography variant="h6" fontWeight={900}>{card.front}</Typography>
                <Typography variant="body2" color="text.secondary">Gợi ý: {card.hint}</Typography>
                <Divider />
                <Typography variant="caption" color="text.secondary">Click để lật mặt sau • {card.page_reference}</Typography>
              </Stack>
            </CardContent>
          </Card>
          <Card className="flip-card-face flip-card-back">
            <CardContent>
              <Stack spacing={1.5}>
                <Stack direction="row" justifyContent="space-between" alignItems="center">
                  <Chip size="small" label={card.topic} color="secondary" />
                  <RotateCcw size={18} />
                </Stack>
                <Typography sx={{ whiteSpace: 'pre-wrap', lineHeight: 1.75 }}>{card.back}</Typography>
                <Stack direction="row" spacing={0.7} flexWrap="wrap" useFlexGap>
                  {(card.tags || []).map((tag) => <Chip key={tag} size="small" label={`#${tag}`} variant="outlined" />)}
                </Stack>
                <Typography variant="caption" color="text.secondary">Click để quay lại mặt trước • {card.page_reference}</Typography>
              </Stack>
            </CardContent>
          </Card>
        </Box>
      </Box>
      <Stack direction="row" spacing={1}>
        <Button fullWidth size="small" color="error" variant="outlined" onClick={() => mark('forgot')}>Chưa nhớ</Button>
        <Button fullWidth size="small" color="warning" variant="outlined" onClick={() => mark('almost')}>Hơi nhớ</Button>
        <Button fullWidth size="small" color="success" variant="contained" onClick={() => mark('known')}>Đã nhớ</Button>
      </Stack>
    </Stack>
  );
}

function FlashcardsView({ flashcards, courseId }) {
  const [progress, setProgress] = React.useState({});

  React.useEffect(() => {
    setProgress(getStoredProgress(courseId));
  }, [courseId]);

  const known = Object.values(progress).filter((value) => value === 'known').length;
  const total = flashcards.length || 1;

  return (
    <Stack spacing={2}>
      <Alert severity="info">
        Flashcard có thể lật qua lại. Sau khi chọn Chưa nhớ / Hơi nhớ / Đã nhớ, trạng thái được lưu trong trình duyệt để ôn lại.
      </Alert>
      <Box>
        <Stack direction="row" justifyContent="space-between" sx={{ mb: 1 }}>
          <Typography fontWeight={900}>Tiến độ nhớ</Typography>
          <Typography>{known}/{flashcards.length}</Typography>
        </Stack>
        <LinearProgress variant="determinate" value={(known / total) * 100} />
      </Box>
      <ResponsiveGrid>
        {flashcards.map((card, index) => (
          <InteractiveFlashcard
            key={`${card.id}-${card.front}`}
            card={card}
            index={index}
            progress={progress}
            setProgress={setProgress}
            courseId={courseId}
          />
        ))}
      </ResponsiveGrid>
    </Stack>
  );
}

function QuizView({ quizzes }) {
  const [answers, setAnswers] = React.useState({});

  return (
    <Stack spacing={2}>
      {quizzes.map((quiz) => {
        const selected = answers[quiz.id];
        const isAnswered = Boolean(selected);
        return (
          <Card key={quiz.id}>
            <CardContent>
              <Stack spacing={2}>
                <Stack direction="row" justifyContent="space-between" alignItems="center" gap={2}>
                  <Chip color="primary" label={`Câu ${quiz.id}`} />
                  <Stack direction="row" spacing={1}>
                    <Chip size="small" label={quiz.difficulty} />
                    <Chip size="small" label={quiz.page_reference} variant="outlined" />
                  </Stack>
                </Stack>
                <Typography fontWeight={900}>{quiz.question}</Typography>
                <ResponsiveGrid gap={1.5}>
                  {Object.entries(quiz.options || {}).map(([key, value]) => {
                    const correct = key === quiz.correct_answer;
                    const chosen = selected === key;
                    const color = isAnswered && correct ? 'success' : isAnswered && chosen ? 'error' : 'primary';
                    return (
                      <Box key={key}>
                        <Button
                          fullWidth
                          variant={isAnswered && (correct || chosen) ? 'contained' : 'outlined'}
                          color={color}
                          disabled={isAnswered}
                          onClick={() => setAnswers((prev) => ({ ...prev, [quiz.id]: key }))}
                          sx={{ justifyContent: 'flex-start', textAlign: 'left', minHeight: 54 }}
                        >
                          {key}. {value}
                        </Button>
                      </Box>
                    );
                  })}
                </ResponsiveGrid>
                {!isAnswered && <Typography variant="body2" color="text.secondary">Gợi ý: {quiz.hint}</Typography>}
                {isAnswered && (
                  <Alert severity={selected === quiz.correct_answer ? 'success' : 'warning'}>
                    <b>Đáp án đúng: {quiz.correct_answer}.</b> {quiz.explanation}
                  </Alert>
                )}
              </Stack>
            </CardContent>
          </Card>
        );
      })}
    </Stack>
  );
}


function formatSlideDate() {
  try {
    return new Date().toLocaleDateString('en-US', {
      month: 'long',
      day: 'numeric',
      year: 'numeric',
    });
  } catch {
    return 'June 18, 2026';
  }
}

function SlidePreview({ slides, courseTitle }) {
  const displayDate = React.useMemo(() => formatSlideDate(), []);
  const compactCourseTitle = courseTitle || 'Bài giảng học thuật';

  return (
    <Stack spacing={2.5}>
      <Alert severity="info">
        Preview đã được nâng cấp theo phong cách slide đại học: khung 16:9, tiêu đề lớn, thanh header/footer, khối nội dung rõ ràng và phần speaker note riêng. Backend đồng thời lưu cả nguồn Marp Markdown và LaTeX Beamer để tiếp tục tinh chỉnh trong Marp hoặc Overleaf.
      </Alert>
      <Stack spacing={3}>
        {slides.map((slide, index) => (
          <Box key={`${slide.title}-${index}`} className="university-slide-shell">
            <Box className="university-slide-topbar">
              <Typography variant="caption" className="slide-top-chip">Hệ thống AI hỗ trợ học tập</Typography>
              <Typography variant="caption" className="slide-top-title">{compactCourseTitle}</Typography>
              <Typography variant="caption" className="slide-top-meta">{displayDate} <span className="slide-sep">•</span> {index + 1} / {slides.length}</Typography>
            </Box>

            <Box className="university-slide-canvas">
              <Box className="university-slide-titleband">
                <Typography className="university-slide-title">{slide.title}</Typography>
              </Box>

              <Box className="university-slide-body">
                <Box className="university-content-card">
                  <Box className="university-content-card-header">
                    <Typography className="university-content-card-header-text">
                      {slide.subtitle || 'Nội dung trọng tâm'}
                    </Typography>
                  </Box>

                  <Box className="university-content-card-inner">
                    {(slide.bullets || []).length > 0 && (
                      <Box component="ul" className="university-bullet-list">
                        {(slide.bullets || []).map((bullet, idx) => (
                          <Box component="li" key={idx} className="university-bullet-item">
                            <span className="university-bullet-dot" />
                            <span>{bullet}</span>
                          </Box>
                        ))}
                      </Box>
                    )}

                    {slide.math_or_key_formula && slide.math_or_key_formula.trim() && (
                      <Box className="university-formula-box">
                        <Typography className="university-formula-label">Công thức / ý chính</Typography>
                        <Typography className="university-formula-text">{slide.math_or_key_formula}</Typography>
                      </Box>
                    )}

                    <Box className="university-speaker-note">
                      <Typography className="university-speaker-note-label">Speaker note</Typography>
                      <Typography className="university-speaker-note-text">{slide.speaker_note}</Typography>
                    </Box>
                  </Box>
                </Box>
              </Box>
            </Box>

            <Box className="university-slide-bottombar">
              <Typography variant="caption" className="slide-bottom-chip">StudyHack Course Compiler</Typography>
              <Typography variant="caption" className="slide-bottom-title">{compactCourseTitle}</Typography>
              <Typography variant="caption" className="slide-bottom-meta">{slide.page_reference}</Typography>
            </Box>
          </Box>
        ))}
      </Stack>
    </Stack>
  );
}

function SlidesView({ course }) {
  const [subTab, setSubTab] = React.useState(0);
  return (
    <Stack spacing={2}>
      <Tabs value={subTab} onChange={(_, next) => setSubTab(next)} variant="scrollable" scrollButtons="auto">
        <Tab label="Preview học thuật" />
        <Tab label="Marp Markdown" />
        <Tab label="LaTeX Beamer / Overleaf" />
      </Tabs>
      <TabPanel value={subTab} index={0}><SlidePreview slides={course.slide_outline || []} courseTitle={course.title} /></TabPanel>
      <TabPanel value={subTab} index={1}><SourceBlock title="slides/slides.md" value={course.slides_marp} /></TabPanel>
      <TabPanel value={subTab} index={2}><SourceBlock title="slides/slides.tex" value={course.slides_latex_beamer} /></TabPanel>
    </Stack>
  );
}

function AudioView({ script }) {
  return (
    <Card>
      <CardContent>
        <Stack spacing={2}>
          <Stack direction="row" spacing={1.5} alignItems="center">
            <Avatar sx={{ bgcolor: 'secondary.main' }}><Headphones size={20} /></Avatar>
            <Box>
              <Typography variant="h6" fontWeight={900}>Audio Podcast Script</Typography>
              <Typography variant="body2" color="text.secondary">Dùng phần này để đọc voice-over hoặc đưa sang TTS sau.</Typography>
            </Box>
          </Stack>
          <Paper variant="outlined" sx={{ p: 3, lineHeight: 1.75, whiteSpace: 'pre-wrap' }}>
            {script}
          </Paper>
        </Stack>
      </CardContent>
    </Card>
  );
}

function QualityView({ report }) {
  if (!report) return null;
  return (
    <Card>
      <CardContent>
        <Stack spacing={2}>
          <Typography variant="h6" fontWeight={900}>Quality Report</Typography>
          <Box>
            <Stack direction="row" justifyContent="space-between" sx={{ mb: 1 }}>
              <Typography>Coverage score</Typography>
              <Typography fontWeight={900}>{report.coverage_score}/100</Typography>
            </Stack>
            <LinearProgress variant="determinate" value={report.coverage_score || 0} />
          </Box>
          <ResponsiveGrid columns={{ xs: 1, md: 3 }} gap={2}>
            <Paper variant="outlined" sx={{ p: 2, borderRadius: 3 }}>
              <Typography fontWeight={900} gutterBottom>Điểm mạnh</Typography>
              {(report.strengths || []).map((item, idx) => <Typography key={idx} variant="body2">• {item}</Typography>)}
            </Paper>
            <Paper variant="outlined" sx={{ p: 2, borderRadius: 3 }}>
              <Typography fontWeight={900} gutterBottom>Điểm còn yếu</Typography>
              {(report.missing_or_weak_points || []).map((item, idx) => <Typography key={idx} variant="body2">• {item}</Typography>)}
            </Paper>
            <Paper variant="outlined" sx={{ p: 2, borderRadius: 3 }}>
              <Typography fontWeight={900} gutterBottom>Cải thiện tiếp</Typography>
              {(report.suggested_next_improvements || []).map((item, idx) => <Typography key={idx} variant="body2">• {item}</Typography>)}
            </Paper>
          </ResponsiveGrid>
        </Stack>
      </CardContent>
    </Card>
  );
}

export default function CourseBuilder() {
  const [file, setFile] = React.useState(null);
  const [course, setCourse] = React.useState(null);
  const [debug, setDebug] = React.useState(null);
  const [tab, setTab] = React.useState(0);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState('');

  async function handleSubmit(event) {
    event.preventDefault();
    if (!file) {
      setError('Chọn một file PDF trước đã.');
      return;
    }

    setLoading(true);
    setError('');
    setCourse(null);
    setDebug(null);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch('/api/course/upload', {
        method: 'POST',
        body: formData,
      });
      const result = await response.json();

      if (!response.ok || result.status !== 'success') {
        throw new Error(result.message || result.detail || 'Upload thất bại.');
      }

      setCourse(result.course);
      setDebug(result.debug);
      setTab(0);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  const courseId = course?.source_file || 'local-course';

  return (
    <Box>
      <AppBar position="sticky" elevation={0} color="transparent" sx={{ backdropFilter: 'blur(16px)', borderBottom: '1px solid rgba(148,163,184,.22)' }}>
        <Container maxWidth="lg">
          <Stack direction="row" alignItems="center" justifyContent="space-between" py={1.5}>
            <Stack direction="row" spacing={1.5} alignItems="center">
              <Avatar sx={{ bgcolor: 'primary.main' }}><BrainCircuit size={22} /></Avatar>
              <Box>
                <Typography fontWeight={950}>StudyHack.AI</Typography>
                <Typography variant="caption" color="text.secondary">Course Compiler v5.5</Typography>
              </Box>
            </Stack>
            <Stack direction="row" spacing={1} sx={{ display: { xs: 'none', sm: 'flex' } }}>
              <Chip icon={<ShieldCheck size={16} />} label="Server-side API" color="success" variant="outlined" />
              <Chip icon={<Layers3 size={16} />} label="Maintainable package" color="primary" variant="outlined" />
            </Stack>
          </Stack>
        </Container>
      </AppBar>

      <Container maxWidth="lg" sx={{ py: { xs: 4, md: 7 } }}>
        <ResponsiveGrid gap={4}>
          <Box>
            <Stack spacing={3}>
              <Box>
                <Chip label="Framework UI • Server-side AI • Course Package" color="primary" />
                <Typography variant="h1" sx={{ mt: 2, fontSize: { xs: 40, md: 62 }, lineHeight: 1.05 }}>
                  Biến PDF thành <span className="gradient-title">học phần học thuật rõ ràng</span>
                </Typography>
                <Typography variant="h6" color="text.secondary" sx={{ mt: 2 }}>
                  Tạo bài giảng sâu, flashcard lật, quiz có giải thích và slide học thuật kiểu đại học. Giao diện được tối ưu lại để dễ đọc, ít “AI-looking” hơn và maintain tốt cho các khóa sau.
                </Typography>
              </Box>

              <Card>
                <CardContent>
                  <Stack component="form" onSubmit={handleSubmit} spacing={2.5}>
                    <Paper className="drop-zone" variant="outlined" sx={{ p: 3, textAlign: 'center' }}>
                      <Stack spacing={2} alignItems="center">
                        <Avatar sx={{ width: 64, height: 64, bgcolor: 'primary.main' }}>
                          <FileUp size={30} />
                        </Avatar>
                        <Box>
                          <Typography fontWeight={900}>Tải lên tài liệu PDF</Typography>
                          <Typography variant="body2" color="text.secondary">Hỗ trợ PDF tối đa 50MB. Với tài liệu scan, bật OCR trong backend trước khi chạy.</Typography>
                        </Box>
                        <Button variant="outlined" component="label" disabled={loading}>
                          Chọn tệp PDF
                          <input
                            hidden
                            type="file"
                            accept="application/pdf,.pdf"
                            onChange={(e) => setFile(e.target.files?.[0] || null)}
                          />
                        </Button>
                        {file && <Chip label={`${file.name} • ${(file.size / 1024 / 1024).toFixed(2)} MB`} />}
                      </Stack>
                    </Paper>

                    {loading && (
                      <Box>
                        <LinearProgress />
                        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                          Đang biên soạn khóa học. Giữ nguyên cả terminal backend và frontend trong lúc xử lý.
                        </Typography>
                      </Box>
                    )}

                    <Button size="large" type="submit" variant="contained" disabled={!file || loading} startIcon={loading ? <CircularProgress size={18} color="inherit" /> : <Sparkles size={18} />}>
                      {loading ? 'Đang tạo khóa học...' : 'Tạo khóa học từ PDF'}
                    </Button>
                  </Stack>
                </CardContent>
              </Card>
            </Stack>
          </Box>

          <Box>
            {course ? <CourseHeader course={course} /> : <EmptyPreview />}
          </Box>
        </ResponsiveGrid>

        {debug && (
          <Alert severity={debug.generation_mode && debug.generation_mode !== 'gemini' ? 'warning' : 'success'} sx={{ mt: 4 }}>
            Backend debug: {debug.pages_extracted} trang, {debug.characters_extracted} ký tự, OCR: {String(debug.ocr_enabled)}.
            {' '}Generation: {debug.generation_mode || 'gemini'}.
            {' '}Key format: {debug.api_key_looks_like_google_key ? 'looks OK' : 'không giống Gemini key chuẩn'}.
            {' '}Course folder: {debug.saved_course_dir}
            {debug.generation_error ? ` • AI error: ${debug.generation_error.slice(0, 220)}` : ''}
          </Alert>
        )}

        {course && (
          <Box sx={{ mt: 4 }}>
            <Card>
              <CardContent>
                <Tabs value={tab} onChange={(_, next) => setTab(next)} variant="scrollable" scrollButtons="auto">
                  <Tab icon={<BookOpen size={18} />} iconPosition="start" label="Bài học" />
                  <Tab icon={<Layers3 size={18} />} iconPosition="start" label="Flashcard" />
                  <Tab icon={<GraduationCap size={18} />} iconPosition="start" label="Quiz" />
                  <Tab icon={<Presentation size={18} />} iconPosition="start" label="Slide" />
                  <Tab icon={<Headphones size={18} />} iconPosition="start" label="Audio" />
                  <Tab icon={<CheckCircle2 size={18} />} iconPosition="start" label="Quality" />
                </Tabs>
                <TabPanel value={tab} index={0}><LessonsView lessons={course.lessons || []} glossary={course.glossary || []} teacherNotes={course.teacher_notes || ''} /></TabPanel>
                <TabPanel value={tab} index={1}><FlashcardsView flashcards={course.flashcards || []} courseId={courseId} /></TabPanel>
                <TabPanel value={tab} index={2}><QuizView quizzes={course.quizzes || []} /></TabPanel>
                <TabPanel value={tab} index={3}><SlidesView course={course} /></TabPanel>
                <TabPanel value={tab} index={4}><AudioView script={course.audio_script || ''} /></TabPanel>
                <TabPanel value={tab} index={5}><QualityView report={course.quality_report} /></TabPanel>
              </CardContent>
            </Card>
          </Box>
        )}
      </Container>

      <Snackbar open={Boolean(error)} autoHideDuration={7000} onClose={() => setError('')}>
        <Alert severity="error" onClose={() => setError('')} sx={{ width: '100%' }}>
          {error}
        </Alert>
      </Snackbar>
    </Box>
  );
}
