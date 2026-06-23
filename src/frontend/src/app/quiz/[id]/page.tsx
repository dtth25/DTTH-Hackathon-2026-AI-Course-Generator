"use client";

import { useState, useEffect, useMemo, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ChevronLeft,
  ChevronRight,
  CheckCircle2,
  XCircle,
  HelpCircle,
  RotateCcw,
  BarChart3,
} from "lucide-react";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
  Button,
  Progress,
  RadioGroup,
  RadioGroupItem,
  Label,
  Separator,
} from "@/components/ui";
import { generateQuiz, type QuizResponse } from "@/lib/api";

/* ── Helpers ───────────────────────────────────────────── */

const DIFFICULTY_LABEL: Record<string, string> = {
  easy: "Dễ",
  medium: "Trung bình",
  hard: "Khó",
};

const DIFFICULTY_COLOR: Record<string, string> = {
  easy: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  medium:
    "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  hard: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
};

/* ── Component ─────────────────────────────────────────── */

export default function QuizPage() {
  const params = useParams();
  const router = useRouter();
  const courseId = params.id as string;

  /* Data state */
  const [quiz, setQuiz] = useState<QuizResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  /* Interaction state */
  const [answers, setAnswers] = useState<Record<number, number>>({});
  const [currentQuestion, setCurrentQuestion] = useState(0);
  const [showResults, setShowResults] = useState(false);

  /* Fetch quiz on mount */
  useEffect(() => {
    async function fetchQuiz() {
      try {
        setLoading(true);
        setError(null);
        const data = await generateQuiz(courseId);
        setQuiz(data);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Không thể tải quiz. Vui lòng thử lại."
        );
      } finally {
        setLoading(false);
      }
    }

    fetchQuiz();
  }, [courseId]);

  /* Derived values */
  const questions = quiz?.questions ?? [];
  const totalQuestions = questions.length;
  const currentQ = questions[currentQuestion];

  const handleSelect = useCallback(
    (value: string) => {
      if (showResults) return;
      const optionIndex = parseInt(value, 10);
      setAnswers((prev) => ({ ...prev, [currentQuestion]: optionIndex }));
    },
    [currentQuestion, showResults]
  );

  const goToQuestion = useCallback(
    (index: number) => {
      if (index >= 0 && index < totalQuestions) {
        setCurrentQuestion(index);
      }
    },
    [totalQuestions]
  );

  const handleShowResults = useCallback(() => {
    setShowResults(true);
  }, []);

  const handleRestart = useCallback(() => {
    setAnswers({});
    setCurrentQuestion(0);
    setShowResults(false);
  }, []);

  /* Scoring */
  const score = useMemo(() => {
    let correct = 0;
    for (let i = 0; i < totalQuestions; i++) {
      if (answers[i] === questions[i]?.correct) {
        correct++;
      }
    }
    return correct;
  }, [answers, questions, totalQuestions]);

  /* ── Loading state ───────────────────────────── */
  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-24 space-y-4">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
        <p className="text-sm text-muted-foreground">
          Đang tạo quiz từ tài liệu...
        </p>
      </div>
    );
  }

  /* ── Error state ─────────────────────────────── */
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-24 space-y-4">
        <HelpCircle className="h-12 w-12 text-destructive" />
        <p className="text-sm text-destructive font-medium">{error}</p>
        <Button variant="outline" onClick={() => router.back()}>
          Quay lại
        </Button>
      </div>
    );
  }

  /* ── Empty state ─────────────────────────────── */
  if (!quiz || totalQuestions === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-24 space-y-4">
        <p className="text-sm text-muted-foreground">
          Quiz trống hoặc không tìm thấy.
        </p>
        <Button variant="outline" onClick={() => router.back()}>
          Quay lại
        </Button>
      </div>
    );
  }

  /* ── Result screen ───────────────────────────── */
  if (showResults) {
    const percentage = Math.round((score / totalQuestions) * 100);
    let resultColor = "text-red-500";
    let resultText = "Cần cố gắng hơn!";
    if (percentage >= 80) {
      resultColor = "text-green-500";
      resultText = "Xuất sắc!";
    } else if (percentage >= 60) {
      resultColor = "text-amber-500";
      resultText = "Khá tốt!";
    } else if (percentage >= 40) {
      resultColor = "text-amber-500";
      resultText = "Có thể làm tốt hơn!";
    }

    return (
      <div className="space-y-6">
        {/* Header */}
        <div className="space-y-2">
          <button
            onClick={() => router.back()}
            className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            <ChevronLeft className="h-4 w-4" />
            Quay lại khóa học
          </button>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">
            Kết quả
          </h1>
          <p className="text-sm text-muted-foreground">{quiz.topic}</p>
        </div>

        {/* Score card */}
        <Card className="text-center py-8">
          <CardContent className="space-y-4">
            <BarChart3 className="h-12 w-12 mx-auto text-primary" />
            <div className={`text-5xl font-bold ${resultColor}`}>
              {score}/{totalQuestions}
            </div>
            <p className="text-lg font-medium">{resultText}</p>
            <Progress value={percentage} className="w-full max-w-xs mx-auto" />
            <p className="text-sm text-muted-foreground">
              {percentage}% câu trả lời đúng
            </p>
          </CardContent>
          <CardFooter className="justify-center gap-3">
            <Button variant="outline" onClick={handleRestart}>
              <RotateCcw className="h-4 w-4 mr-1" />
              Làm lại
            </Button>
            <Button onClick={() => router.back()}>Quay lại khóa học</Button>
          </CardFooter>
        </Card>

        {/* Review answers */}
        <div className="space-y-3">
          <h2 className="text-lg font-medium">Chi tiết câu trả lời</h2>
          {questions.map((q, idx) => {
            const userAnswer = answers[idx];
            const isCorrect = userAnswer === q.correct;
            const isAnswered = userAnswer !== undefined;

            return (
              <Card
                key={idx}
                className={`border-l-4 ${
                  isAnswered
                    ? isCorrect
                      ? "border-l-green-500"
                      : "border-l-red-500"
                    : "border-l-muted"
                }`}
              >
                <CardHeader className="pb-2">
                  <div className="flex items-start justify-between gap-2">
                    <CardTitle className="text-sm font-medium">
                      Câu {idx + 1}: {q.question}
                    </CardTitle>
                    {isAnswered ? (
                      isCorrect ? (
                        <CheckCircle2 className="h-5 w-5 shrink-0 text-green-500" />
                      ) : (
                        <XCircle className="h-5 w-5 shrink-0 text-red-500" />
                      )
                    ) : (
                      <HelpCircle className="h-5 w-5 shrink-0 text-muted-foreground" />
                    )}
                  </div>
                </CardHeader>
                <CardContent className="space-y-1 pb-3">
                  {q.options.map((opt, oi) => {
                    let optClass = "text-sm px-3 py-1.5 rounded-md";
                    if (oi === q.correct) {
                      optClass += " bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400";
                    } else if (oi === userAnswer && oi !== q.correct) {
                      optClass += " bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400";
                    } else {
                      optClass += " text-muted-foreground";
                    }
                    return (
                      <div key={oi} className={optClass}>
                        {opt}
                      </div>
                    );
                  })}
                  {q.explanation && (
                    <p className="text-xs text-muted-foreground mt-2 italic">
                      💡 {q.explanation}
                    </p>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      </div>
    );
  }

  /* ── Quiz screen ─────────────────────────────── */
  const answeredCount = Object.keys(answers).length;
  const progressValue = totalQuestions > 0 ? (answeredCount / totalQuestions) * 100 : 0;

  return (
    <div className="space-y-6 max-w-2xl mx-auto">
      {/* Header */}
      <div className="space-y-2">
        <button
          onClick={() => router.back()}
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ChevronLeft className="h-4 w-4" />
          Quay lại khóa học
        </button>
        <div className="flex items-center justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-foreground">
              {quiz.topic}
            </h1>
            <p className="text-sm text-muted-foreground">
              Khóa học: {courseId.slice(0, 8)}...
            </p>
          </div>
          <span
            className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${DIFFICULTY_COLOR[quiz.difficulty] ?? DIFFICULTY_COLOR.medium}`}
          >
            {DIFFICULTY_LABEL[quiz.difficulty] ?? quiz.difficulty}
          </span>
        </div>
      </div>

      {/* Progress bar */}
      <div className="space-y-1">
        <div className="flex justify-between text-xs text-muted-foreground">
          <span>
            Đã trả lời: {answeredCount}/{totalQuestions}
          </span>
          <span>
            Câu {currentQuestion + 1}/{totalQuestions}
          </span>
        </div>
        <Progress value={progressValue} />
      </div>

      <Separator />

      {/* Question card */}
      <Card>
        <CardHeader>
          <CardDescription className="text-xs font-medium uppercase tracking-wide">
            Câu {currentQuestion + 1} / {totalQuestions}
          </CardDescription>
          <CardTitle className="text-base font-medium leading-relaxed">
            {currentQ.question}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <RadioGroup
            value={
              answers[currentQuestion] !== undefined
                ? String(answers[currentQuestion])
                : undefined
            }
            onValueChange={handleSelect}
            className="gap-2"
          >
            {currentQ.options.map((option, idx) => {
              const isSelected = answers[currentQuestion] === idx;
              const hasAnswer = answers[currentQuestion] !== undefined;
              const isCorrect = idx === currentQ.correct;

              let optionClass =
                "flex items-center gap-3 rounded-lg border px-4 py-3 text-sm transition-all cursor-pointer";
              if (hasAnswer) {
                if (isCorrect) {
                  optionClass += " border-green-500 bg-green-50 dark:bg-green-950/20";
                } else if (isSelected && !isCorrect) {
                  optionClass += " border-red-500 bg-red-50 dark:bg-red-950/20";
                } else {
                  optionClass += " border-border opacity-60";
                }
              } else {
                optionClass +=
                  " border-border hover:border-primary hover:bg-muted/50";
              }

              return (
                <Label key={idx} className={optionClass}>
                  <RadioGroupItem
                    value={String(idx)}
                    disabled={hasAnswer}
                    className={
                      hasAnswer && isCorrect
                        ? "border-green-500 text-green-500 data-[state=checked]:bg-green-500 data-[state=checked]:border-green-500"
                        : hasAnswer && isSelected && !isCorrect
                          ? "border-red-500 text-red-500 data-[state=checked]:bg-red-500 data-[state=checked]:border-red-500"
                          : ""
                    }
                  />
                  <span className="flex-1">{option}</span>
                  {hasAnswer && isCorrect && (
                    <CheckCircle2 className="h-4 w-4 shrink-0 text-green-500" />
                  )}
                  {hasAnswer && isSelected && !isCorrect && (
                    <XCircle className="h-4 w-4 shrink-0 text-red-500" />
                  )}
                </Label>
              );
            })}
          </RadioGroup>

          {/* Explanation */}
          {answers[currentQuestion] !== undefined && currentQ.explanation && (
            <div className="mt-4 rounded-lg bg-muted/50 px-4 py-3 text-sm text-muted-foreground">
              <p className="font-medium text-foreground mb-1">💡 Giải thích:</p>
              <p>{currentQ.explanation}</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Navigation */}
      <div className="flex items-center justify-between gap-3">
        <Button
          variant="outline"
          disabled={currentQuestion === 0}
          onClick={() => goToQuestion(currentQuestion - 1)}
        >
          <ChevronLeft className="h-4 w-4 mr-1" />
          Câu trước
        </Button>

        <span className="text-xs text-muted-foreground">
          {currentQuestion + 1} / {totalQuestions}
        </span>

        {currentQuestion < totalQuestions - 1 ? (
          <Button
            variant="outline"
            onClick={() => goToQuestion(currentQuestion + 1)}
          >
            Câu sau
            <ChevronRight className="h-4 w-4 ml-1" />
          </Button>
        ) : (
          <Button onClick={handleShowResults}>
            Xem kết quả
            <BarChart3 className="h-4 w-4 ml-1" />
          </Button>
        )}
      </div>
    </div>
  );
}