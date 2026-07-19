"use client";

import { useOrganization, useUser } from "@clerk/nextjs";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ClipboardList, Clock, Trash2 } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useState } from "react";
import { useConfirm } from "@/components/confirm-provider";
import { EmptyState } from "@/components/empty-state";
import { ErrorState } from "@/components/error-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "@/components/ui/toast";
import { useApiClient } from "@/lib/api/useApiClient";
import type { components } from "@/lib/api/schema";
import { canCreateAssignment, canDeleteAssignment } from "@/lib/assignmentPermissions";
import { dueStatus } from "@/lib/assignmentDueDate";
import { orgCapability } from "@/lib/orgRole";

type Assignment = components["schemas"]["AssignmentRead"];
type Submission = components["schemas"]["AssignmentSubmissionRead"];
type Translate = ReturnType<typeof useTranslations>;

const selectClassName =
  "h-10 rounded-lg border border-border bg-background px-2.5 text-sm text-foreground focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none disabled:opacity-50";

/** Due-date badge — overdue pairs a warning icon with the label (never color alone,
 * FRONTEND.md §2.5); upcoming/none stay quiet, plain muted text or nothing. */
function DueBadge({ dueAt, t }: { dueAt: string | null | undefined; t: Translate }) {
  const status = dueStatus(dueAt);
  if (status === "none") return null;
  if (status === "overdue") {
    return (
      <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-warning-bg px-2 py-0.5 text-xs font-medium text-warning">
        <Clock className="size-3" aria-hidden />
        {t("Assignments.overdueBadge")}
      </span>
    );
  }
  return (
    <span className="shrink-0 text-xs text-muted-foreground">
      {t("Assignments.dueOn", { date: new Date(dueAt as string).toLocaleDateString() })}
    </span>
  );
}

function TeacherAssignmentCard({
  assignment,
  subjectName,
  canDelete,
  deleting,
  onDelete,
  expanded,
  onToggleSubmissions,
  submissionsQuery,
  t,
}: {
  assignment: Assignment;
  subjectName: string;
  canDelete: boolean;
  deleting: boolean;
  onDelete: () => void;
  expanded: boolean;
  onToggleSubmissions: () => void;
  submissionsQuery: {
    isLoading: boolean;
    isError: boolean;
    data: Submission[] | undefined;
  } | null;
  t: Translate;
}) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-3 py-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium text-foreground">{assignment.title}</p>
            <p className="text-xs text-muted-foreground">{subjectName}</p>
            {assignment.description && (
              <p className="mt-1 text-sm text-muted-foreground">{assignment.description}</p>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <DueBadge dueAt={assignment.due_at} t={t} />
            {canDelete && (
              <Button
                variant="destructive"
                size="icon-sm"
                aria-label={t("Assignments.deleteAriaLabel", { title: assignment.title })}
                disabled={deleting}
                onClick={onDelete}
              >
                <Trash2 className="size-3.5" />
              </Button>
            )}
          </div>
        </div>

        <Button variant="outline" size="sm" className="w-fit" onClick={onToggleSubmissions}>
          {expanded ? t("Assignments.hideSubmissions") : t("Assignments.viewSubmissions")}
        </Button>

        {expanded && submissionsQuery && (
          <div className="rounded-lg border border-border p-3">
            <p className="mb-2 text-xs font-medium text-muted-foreground">
              {t("Assignments.submissionsReceivedLabel")}
            </p>
            {submissionsQuery.isLoading && (
              <p className="text-sm text-muted-foreground">{t("Common.loading")}</p>
            )}
            {submissionsQuery.isError && (
              <p className="text-sm text-destructive">{t("Assignments.submissionsLoadError")}</p>
            )}
            {submissionsQuery.data?.length === 0 && (
              <p className="text-sm text-muted-foreground">{t("Assignments.noSubmissionsYet")}</p>
            )}
            <ul className="flex flex-col gap-2">
              {submissionsQuery.data?.map((submission) => (
                <li
                  key={submission.id}
                  className="flex items-center justify-between gap-2 text-sm"
                >
                  <span className="truncate text-foreground">{submission.owner_id}</span>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {new Date(submission.completed_at).toLocaleDateString()}
                    {submission.score != null
                      ? ` · ${t("Assignments.scoreLabel", { score: submission.score })}`
                      : ""}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function StudentAssignmentCard({
  assignment,
  subjectName,
  mySubmission,
  isLoading,
  isSubmitting,
  onSubmit,
  t,
}: {
  assignment: Assignment;
  subjectName: string;
  mySubmission: Submission | null | undefined;
  isLoading: boolean;
  isSubmitting: boolean;
  onSubmit: (payload: { score: number | null; note: string | null }) => void;
  t: Translate;
}) {
  const [score, setScore] = useState("");
  const [note, setNote] = useState("");
  const submitted = mySubmission != null;

  return (
    <Card>
      <CardContent className="flex flex-col gap-3 py-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium text-foreground">{assignment.title}</p>
            <p className="text-xs text-muted-foreground">{subjectName}</p>
            {assignment.description && (
              <p className="mt-1 text-sm text-muted-foreground">{assignment.description}</p>
            )}
          </div>
          <DueBadge dueAt={assignment.due_at} t={t} />
        </div>

        {isLoading ? (
          <p className="text-sm text-muted-foreground">{t("Common.loading")}</p>
        ) : submitted && mySubmission ? (
          <div className="flex items-center gap-2 rounded-lg bg-success-bg px-3 py-2 text-sm text-success">
            <CheckCircle2 className="size-4 shrink-0" aria-hidden />
            <span>
              {t("Assignments.completedOn", {
                date: new Date(mySubmission.completed_at).toLocaleDateString(),
              })}
              {mySubmission.score != null
                ? ` · ${t("Assignments.scoreLabel", { score: mySubmission.score })}`
                : ""}
            </span>
          </div>
        ) : (
          <form
            className="flex flex-wrap items-end gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              onSubmit({
                score: score.trim() ? Number(score) : null,
                note: note.trim() || null,
              });
            }}
          >
            <div className="flex flex-col gap-1">
              <Label htmlFor={`score-${assignment.id}`} className="text-xs">
                {t("Assignments.scoreOptionalLabel")}
              </Label>
              <Input
                id={`score-${assignment.id}`}
                type="number"
                min={0}
                max={100}
                className="w-20"
                value={score}
                disabled={isSubmitting}
                onChange={(event) => setScore(event.target.value)}
              />
            </div>
            <div className="flex min-w-40 flex-1 flex-col gap-1">
              <Label htmlFor={`note-${assignment.id}`} className="text-xs">
                {t("Assignments.noteOptionalLabel")}
              </Label>
              <Input
                id={`note-${assignment.id}`}
                maxLength={2000}
                value={note}
                disabled={isSubmitting}
                onChange={(event) => setNote(event.target.value)}
              />
            </div>
            <Button type="submit" size="sm" disabled={isSubmitting}>
              {isSubmitting ? t("Assignments.submitting") : t("Assignments.markComplete")}
            </Button>
          </form>
        )}
      </CardContent>
    </Card>
  );
}

export default function AssignmentsPage() {
  const api = useApiClient();
  const queryClient = useQueryClient();
  const confirm = useConfirm();
  const t = useTranslations();
  const { user } = useUser();
  const { isLoaded, organization, membership } = useOrganization();
  const capability = orgCapability(membership?.role);
  const isTeacher = capability === "teacher";

  const [title, setTitle] = useState("");
  const [subjectId, setSubjectId] = useState("");
  const [description, setDescription] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [quizId, setQuizId] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const assignmentsQuery = useQuery({
    queryKey: ["assignments"],
    queryFn: async () => {
      const { data, error } = await api.GET("/assignments");
      if (error) throw error;
      return data;
    },
    enabled: !!organization,
  });

  // Used both to populate the teacher's subject picker and to resolve a friendly subject
  // name for every assignment card — returns the caller's own + active-org subjects.
  const subjectsQuery = useQuery({
    queryKey: ["subjects"],
    queryFn: async () => {
      const { data, error } = await api.GET("/subjects");
      if (error) throw error;
      return data;
    },
    enabled: !!organization,
  });
  const subjectNameById = new Map((subjectsQuery.data ?? []).map((s) => [s.id, s.name]));

  const quizzesQuery = useQuery({
    queryKey: ["subjects", subjectId, "quizzes"],
    queryFn: async () => {
      const { data, error } = await api.GET("/subjects/{subject_id}/quizzes", {
        params: { path: { subject_id: subjectId } },
      });
      if (error) throw error;
      return data;
    },
    enabled: isTeacher && !!subjectId,
  });

  // Each student's own submission status, fetched per assignment (mirrors the sidebar
  // preview pattern in the Ask page) — a 404 just means "not submitted yet", not a
  // real error, so it resolves to `null` instead of throwing.
  const assignments = assignmentsQuery.data ?? [];
  const mySubmissionQueries = useQueries({
    queries: assignments.map((assignment) => ({
      queryKey: ["assignments", assignment.id, "my-submission"],
      queryFn: async () => {
        const { data, error, response } = await api.GET(
          "/assignments/{assignment_id}/my-submission",
          { params: { path: { assignment_id: assignment.id } } },
        );
        if (error) {
          if (response.status === 404) return null;
          throw error;
        }
        return data;
      },
      enabled: !isTeacher,
    })),
  });

  const submissionsQuery = useQuery({
    queryKey: ["assignments", expandedId, "submissions"],
    queryFn: async () => {
      const { data, error } = await api.GET("/assignments/{assignment_id}/submissions", {
        params: { path: { assignment_id: expandedId as string } },
      });
      if (error) throw error;
      return data;
    },
    enabled: isTeacher && !!expandedId,
  });

  const createAssignment = useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST("/assignments", {
        body: {
          title: title.trim(),
          subject_id: subjectId,
          description: description.trim() || null,
          quiz_id: quizId || null,
          due_at: dueAt ? new Date(dueAt).toISOString() : null,
        },
      });
      if (error) {
        toast.error(t("Assignments.createErrorTitle"), t("Common.tryAgain"));
        throw error;
      }
      return data;
    },
    onSuccess: (data) => {
      setTitle("");
      setDescription("");
      setDueAt("");
      setQuizId("");
      queryClient.invalidateQueries({ queryKey: ["assignments"] });
      toast.success(t("Assignments.createSuccess"), data.title);
    },
  });

  const deleteAssignment = useMutation({
    mutationFn: async (assignmentId: string) => {
      const { error, response } = await api.DELETE("/assignments/{assignment_id}", {
        params: { path: { assignment_id: assignmentId } },
      });
      if (error) {
        throw new Error(
          response.status === 404
            ? t("Assignments.deleteNotFound")
            : t("Assignments.deleteGenericError"),
        );
      }
    },
    onSuccess: (_data, assignmentId) => {
      queryClient.invalidateQueries({ queryKey: ["assignments"] });
      if (expandedId === assignmentId) setExpandedId(null);
      toast.success(t("Assignments.deleteSuccess"));
    },
    onError: (error: Error) => {
      toast.error(t("Assignments.deleteErrorTitle"), error.message);
    },
  });

  const submitAssignment = useMutation({
    mutationFn: async ({
      assignmentId,
      score,
      note,
    }: {
      assignmentId: string;
      score: number | null;
      note: string | null;
    }) => {
      const { data, error } = await api.POST("/assignments/{assignment_id}/submit", {
        params: { path: { assignment_id: assignmentId } },
        body: { score, note },
      });
      if (error) {
        toast.error(t("Assignments.submitErrorTitle"), t("Common.tryAgain"));
        throw error;
      }
      return data;
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: ["assignments", variables.assignmentId, "my-submission"],
      });
      toast.success(t("Assignments.submitSuccess"));
    },
  });

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <span className="flex size-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <ClipboardList className="size-5" aria-hidden />
          </span>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">
            {t("Assignments.heading")}
          </h1>
        </div>
        <p className="text-sm text-muted-foreground">
          {isTeacher ? t("Assignments.teacherDescription") : t("Assignments.studentDescription")}
        </p>
      </header>

      {!isLoaded ? (
        <p className="text-sm text-muted-foreground" aria-live="polite">
          {t("Assignments.loading")}
        </p>
      ) : !organization ? (
        <EmptyState
          icon={ClipboardList}
          title={t("Assignments.noOrgTitle")}
          description={t("Assignments.noOrgDescription")}
          action={
            <Button nativeButton={false} render={<Link href="/team">{t("Assignments.goToTeam")}</Link>} />
          }
        />
      ) : (
        <>
          {canCreateAssignment(capability) && (
            <Card>
              <CardHeader>
                <CardTitle>{t("Assignments.createTitle")}</CardTitle>
              </CardHeader>
              <CardContent>
                <form
                  className="flex flex-col gap-4"
                  onSubmit={(event) => {
                    event.preventDefault();
                    if (!createAssignment.isPending && title.trim() && subjectId) {
                      createAssignment.mutate();
                    }
                  }}
                >
                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="assignment-title">{t("Assignments.titleLabel")}</Label>
                    <Input
                      id="assignment-title"
                      value={title}
                      maxLength={300}
                      placeholder={t("Assignments.titlePlaceholder")}
                      disabled={createAssignment.isPending}
                      onChange={(event) => setTitle(event.target.value)}
                    />
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="assignment-subject">{t("Assignments.subjectLabel")}</Label>
                    <select
                      id="assignment-subject"
                      value={subjectId}
                      disabled={createAssignment.isPending}
                      onChange={(event) => {
                        setSubjectId(event.target.value);
                        setQuizId("");
                      }}
                      className={selectClassName}
                    >
                      <option value="">{t("Assignments.subjectPlaceholder")}</option>
                      {subjectsQuery.data?.map((subject) => (
                        <option key={subject.id} value={subject.id}>
                          {subject.name}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <Label htmlFor="assignment-description">
                      {t("Assignments.descriptionLabel")}
                    </Label>
                    <Textarea
                      id="assignment-description"
                      value={description}
                      maxLength={5000}
                      placeholder={t("Assignments.descriptionPlaceholder")}
                      disabled={createAssignment.isPending}
                      onChange={(event) => setDescription(event.target.value)}
                    />
                  </div>

                  <div className="flex flex-wrap gap-4">
                    <div className="flex flex-col gap-1.5">
                      <Label htmlFor="assignment-due">{t("Assignments.dueDateLabel")}</Label>
                      <Input
                        id="assignment-due"
                        type="date"
                        className="w-40"
                        value={dueAt}
                        disabled={createAssignment.isPending}
                        onChange={(event) => setDueAt(event.target.value)}
                      />
                    </div>
                    <div className="flex flex-col gap-1.5">
                      <Label htmlFor="assignment-quiz">{t("Assignments.quizLabel")}</Label>
                      <select
                        id="assignment-quiz"
                        value={quizId}
                        disabled={createAssignment.isPending || !subjectId}
                        onChange={(event) => setQuizId(event.target.value)}
                        className={`${selectClassName} w-56`}
                      >
                        <option value="">{t("Assignments.quizNone")}</option>
                        {quizzesQuery.data?.map((quiz) => (
                          <option key={quiz.id} value={quiz.id}>
                            {quiz.title || t("Quizzes.untitled")}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <Button
                    type="submit"
                    className="w-fit"
                    disabled={createAssignment.isPending || !title.trim() || !subjectId}
                  >
                    {createAssignment.isPending ? t("Assignments.creating") : t("Assignments.create")}
                  </Button>
                </form>
              </CardContent>
            </Card>
          )}

          {assignmentsQuery.isLoading && (
            <p className="text-sm text-muted-foreground">{t("Common.loading")}</p>
          )}
          {assignmentsQuery.isError && (
            <ErrorState
              message={t("Assignments.loadError")}
              retryLabel={t("Common.retry")}
              onRetry={() => assignmentsQuery.refetch()}
            />
          )}
          {assignmentsQuery.data?.length === 0 && (
            <EmptyState icon={ClipboardList} title={t("Assignments.empty")} />
          )}

          <ul className="flex flex-col gap-3">
            {assignments.map((assignment, index) => {
              const subjectName =
                subjectNameById.get(assignment.subject_id) ?? t("Common.subjectFallback");

              if (isTeacher) {
                const expanded = expandedId === assignment.id;
                return (
                  <li key={assignment.id}>
                    <TeacherAssignmentCard
                      assignment={assignment}
                      subjectName={subjectName}
                      canDelete={canDeleteAssignment(user?.id, assignment.owner_id, capability)}
                      deleting={
                        deleteAssignment.isPending && deleteAssignment.variables === assignment.id
                      }
                      onDelete={async () => {
                        const ok = await confirm({
                          title: t("Assignments.deleteConfirmTitle", { title: assignment.title }),
                          description: t("Common.cantUndo"),
                          destructive: true,
                        });
                        if (!ok) return;
                        deleteAssignment.mutate(assignment.id);
                      }}
                      expanded={expanded}
                      onToggleSubmissions={() => setExpandedId(expanded ? null : assignment.id)}
                      submissionsQuery={
                        expanded
                          ? {
                              isLoading: submissionsQuery.isLoading,
                              isError: submissionsQuery.isError,
                              data: submissionsQuery.data,
                            }
                          : null
                      }
                      t={t}
                    />
                  </li>
                );
              }

              const submissionResult = mySubmissionQueries[index];
              return (
                <li key={assignment.id}>
                  <StudentAssignmentCard
                    assignment={assignment}
                    subjectName={subjectName}
                    mySubmission={submissionResult?.data}
                    isLoading={submissionResult?.isLoading ?? false}
                    isSubmitting={
                      submitAssignment.isPending &&
                      submitAssignment.variables?.assignmentId === assignment.id
                    }
                    onSubmit={(payload) =>
                      submitAssignment.mutate({ assignmentId: assignment.id, ...payload })
                    }
                    t={t}
                  />
                </li>
              );
            })}
          </ul>
        </>
      )}
    </div>
  );
}
