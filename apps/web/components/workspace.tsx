"use client";

import { useRef, useState } from "react";
import Image from "next/image";
import { Dialog } from "radix-ui";
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  CheckCheck,
  ChevronRight,
  CircleHelp,
  Clock3,
  Compass,
  GitBranch,
  GraduationCap,
  Layers3,
  Leaf,
  Lightbulb,
  Map,
  Plus,
  RotateCcw,
  Sparkles,
  Sprout,
  Upload,
  X,
  Zap,
} from "lucide-react";
import { Button } from "./ui/button";
import { KnowledgeMap } from "./knowledge-map";
import { vi as t } from "@/messages/vi";
import type { WebConfig } from "@/lib/config";
import { getLessonFixture } from "@/lib/fixtures";
import { validateFile } from "@/lib/safety";
import { useLearning } from "./use-learning";
import { SourceLink } from "./source-link";
import { ErrorState, Loading } from "./async-state";
import { TracePanel } from "./trace-panel";
import type { DemoScenario } from "@/lib/data-client";
import type { KnowledgeGraph } from "@/lib/contracts";

type Screen =
  "overview" | "map" | "learn" | "reviews" | "sources" | "about" | "research";
const navigation = [
  { id: "overview", icon: Compass },
  { id: "map", icon: Map },
  { id: "learn", icon: BookOpen },
  { id: "reviews", icon: RotateCcw },
] as const;

function Sena({ size = 100 }: { size?: number }) {
  return (
    <Image src="/sena.svg" width={size} height={size} alt={t.sena} priority />
  );
}
function Legend() {
  return (
    <div className="legend">
      <span>
        <i className="mastered-dot" />
        {t.mastered}
      </span>
      <span>
        <i className="learning-dot" />
        {t.learning}
      </span>
      <span>
        <i />
        {t.locked}
      </span>
    </div>
  );
}

export function Workspace({ config }: { config: WebConfig }) {
  const learning = useLearning(config);
  const { graph, selected, setSelected, lessons, snapshot, busy, errors } =
    learning;
  const [screen, setScreen] = useState<Screen>("overview");
  const [topicOpen, setTopicOpen] = useState(false);
  const [traceOpen, setTraceOpen] = useState(false);
  const [goal, setGoal] = useState("");
  const [mode, setMode] = useState<"quick" | "deep">("quick");
  const [tier, setTier] = useState<"free" | "pro">("free");
  const [file, setFile] = useState<File | null>(null);
  const [uploadConsent, setUploadConsent] = useState(false);
  const [fileError, setFileError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const [formError, setFormError] = useState("");
  const [upgradeOpen, setUpgradeOpen] = useState(false);
  const [scenario, setScenario] = useState<DemoScenario>("normal");
  const [traceIndex, setTraceIndex] = useState(-1);
  const [submitted, setSubmitted] = useState({
    goal: "",
    fileName: "",
    mode: "quick" as "quick" | "deep",
  });
  const mainRef = useRef<HTMLElement>(null);
  const lesson = lessons[selected];
  const item = lesson?.item;
  const answer = lesson?.answer ?? null;
  const result = lesson?.result;
  const hintCount = lesson?.hints.length ?? 0;
  const reviewDue = learning.reviews.length > 0;
  const concept = graph.nodes.find((node) => node.slug === selected);
  const conceptIndex = graph.nodes.findIndex(
    (node) => node.slug === concept?.slug,
  );
  const fixture = config.mode === "mock" ? getLessonFixture(selected) : null;
  const uploadEnabled =
    config.mode === "mock" || !!(config.uploadField && config.uploadMaxBytes);
  const inFlight = Object.values(busy).some(Boolean);
  const traces = lesson?.traces ?? [];
  const trace = traces[traceIndex < 0 ? traces.length - 1 : traceIndex];
  const subjectTitle =
    config.mode === "mock" ? t.python : learning.subject || t.flow.noData;
  const sources =
    snapshot?.sources ??
    (config.mode === "mock"
      ? [
          {
            title: t.sourceBook,
            publisher: t.sourceAuthor,
            url: "https://allendowney.github.io/ThinkPython/",
            license: t.sourceLicense,
          },
        ]
      : []);
  function navigate(next: Screen) {
    setScreen(next);
    mainRef.current?.focus();
    if (next === "learn" && config.mode === "mock") void learning.loadLesson();
    if (next === "reviews") void learning.loadReviews();
  }
  function selectNode(slug: string) {
    setSelected(slug);
    setTraceIndex(-1);
    if (config.mode === "mock") void learning.loadLesson(slug);
  }
  function showTrace() {
    if (config.mode === "mock") void learning.loadLesson();
    setTraceIndex(-1);
    setTraceOpen(true);
  }
  async function startResearch() {
    if (
      (!goal.trim() && !learning.upload) ||
      goal.length > 500 ||
      (learning.upload && !learning.upload.text_ok)
    ) {
      setFormError(goal.length > 500 ? t.flow.goalLength : t.flow.goalInvalid);
      return;
    }
    if (mode === "deep" && tier !== "pro") {
      setUpgradeOpen(true);
      return;
    }
    setFormError("");
    const created = await learning.createTopic({
      ...(goal.trim() ? { goal_vi: goal.trim().normalize("NFC") } : {}),
      ...(learning.upload ? { upload_id: learning.upload.upload_id } : {}),
      mode,
      tier,
    });
    if (created) {
      setSubmitted({ goal: goal.trim(), fileName: file?.name ?? "", mode });
      setTopicOpen(false);
      navigate("research");
    }
  }
  async function chooseFile(candidate?: File) {
    if (!candidate || !uploadConsent) return;
    learning.clearUpload();
    setFile(candidate);
    const invalid = validateFile(candidate, config.uploadMaxBytes);
    setFileError(
      invalid === "format"
        ? t.flow.unsupportedFile
        : invalid === "size"
          ? t.flow.invalidSize
          : invalid === "unconfigured"
            ? t.flow.uploadDisabled
            : "",
    );
    if (!invalid) await learning.uploadFile(candidate, uploadConsent);
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        {t.flow.skip}
      </a>
      <aside className="sidebar">
        <button className="brand" onClick={() => navigate("overview")}>
          <span className="brand-symbol">
            <GitBranch size={25} />
          </span>
          {t.app}
          <span className="brand-period">.</span>
        </button>
        <div className="sidebar-caption">{t.workspace}</div>
        <nav className="primary-nav" aria-label={t.workspace}>
          {navigation.map(({ id, icon: Icon }) => (
            <button
              key={id}
              aria-label={t.nav[id]}
              className={screen === id ? "active" : ""}
              aria-current={screen === id ? "page" : undefined}
              onClick={() => navigate(id)}
            >
              <Icon size={19} />
              <span>{t.nav[id]}</span>
              {id === "reviews" && reviewDue && (
                <span className="nav-badge">{learning.reviews.length}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-caption resources-caption">{t.library}</div>
        <nav className="secondary-nav" aria-label={t.library}>
          <button
            className={screen === "sources" ? "active" : ""}
            onClick={() => navigate("sources")}
          >
            <Layers3 size={18} />
            {t.sources}
          </button>
          <button
            className={screen === "about" ? "active" : ""}
            onClick={() => navigate("about")}
          >
            <CircleHelp size={18} />
            {t.settings}
          </button>
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-sena">
            <span>
              <Leaf size={18} />
              {t.tagline}
            </span>
            <p>{t.senaTag}</p>
          </div>
          <div className="profile">
            <span className="avatar">
              <Sprout size={20} />
            </span>
            <div>
              <strong>{t.learner}</strong>
              <small>{t.learnerSub}</small>
            </div>
          </div>
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div className="breadcrumb">
            {t.workspace}
            <ChevronRight size={14} />
            <strong>
              {screen in t.nav
                ? t.nav[screen as keyof typeof t.nav]
                : screen === "research"
                  ? t.flow.researchTitle
                  : screen === "sources"
                    ? t.sources
                    : t.settings}
            </strong>
          </div>
          <div className="topbar-right">
            <span className="mock-badge">
              <i />
              {config.mode === "mock" ? t.mock : t.flow.api}
            </span>
            <div
              className="tier-switch"
              role="group"
              aria-label={
                config.mode === "mock" ? t.flow.demoTier : t.flow.apiTier
              }
            >
              <button
                aria-pressed={tier === "free"}
                onClick={() => {
                  setTier("free");
                  setMode("quick");
                }}
                className={tier === "free" ? "chosen" : ""}
              >
                {t.free}
              </button>
              <button
                aria-pressed={tier === "pro"}
                onClick={() => setUpgradeOpen(true)}
                className={tier === "pro" ? "chosen" : ""}
              >
                <Sparkles size={12} />
                {t.pro}
              </button>
            </div>
            <span className="small-avatar">
              <Sprout size={17} />
            </span>
          </div>
        </header>

        <main id="main-content" ref={mainRef} tabIndex={-1}>
          <nav className="mobile-resources" aria-label={t.flow.mobileResources}>
            <button onClick={() => navigate("sources")}>{t.sources}</button>
            <button onClick={() => navigate("about")}>{t.settings}</button>
            {learning.topicId && (
              <button onClick={() => navigate("research")}>
                {t.flow.resume}
              </button>
            )}
          </nav>
          {config.mode === "api" && (
            <p className="mode-notice">{t.flow.apiNotice}</p>
          )}
          {screen === "overview" && (
            <>
              <section className="welcome">
                <div>
                  <p className="eyebrow">
                    <span className="sun-mark">✳</span>
                    {t.hello}
                  </p>
                  <h1>
                    {t.headline}
                    <br />
                    <span>{t.headlineAccent}</span>
                  </h1>
                  <p className="welcome-description">{t.intro}</p>
                </div>
                <Button variant="secondary" onClick={() => setTopicOpen(true)}>
                  <Plus size={17} />
                  {t.newTopic}
                </Button>
              </section>
              <section className="path-summary">
                <div className="subject-icon">
                  <GraduationCap size={26} />
                </div>
                <div className="subject-name">
                  <p className="eyebrow">{t.myPath}</p>
                  <h2>{subjectTitle}</h2>
                  <span>{config.mode === "mock" ? t.subject : t.flow.api}</span>
                </div>
                <div className="path-stat">
                  <strong>{graph.nodes.length}</strong>
                  <span>{t.conceptCount}</span>
                </div>
                <div className="path-stat">
                  <strong>
                    {graph.nodes.filter((n) => n.mastered).length}
                    <span>/{graph.nodes.length}</span>
                  </strong>
                  <span>{t.mastered}</span>
                </div>
                <div className="path-progress">
                  <div className="progress-track">
                    <span
                      style={{
                        width: `${graph.nodes.length ? (graph.nodes.filter((n) => n.mastered).length / graph.nodes.length) * 100 : 0}%`,
                      }}
                    />
                  </div>
                  <span>{t.date}</span>
                </div>
                <Button disabled={!selected} onClick={() => navigate("learn")}>
                  {t.continue}
                  <ArrowRight size={16} />
                </Button>
              </section>
              <div className="overview-grid">
                <section className="panel map-panel">
                  <div className="panel-heading">
                    <div>
                      <p className="eyebrow">
                        <GitBranch size={14} />
                        {t.nav.map}
                      </p>
                      <h2>{t.mapTitle}</h2>
                      <p>{t.mapSubtitle}</p>
                    </div>
                    <button
                      className="text-button"
                      onClick={() => navigate("map")}
                    >
                      {t.viewMap}
                      <ArrowRight size={15} />
                    </button>
                  </div>
                  {
                    <MapContent
                      graph={graph}
                      selected={selected}
                      loading={busy.graph}
                      error={errors.graph}
                      onRetry={() => void learning.reloadGraph()}
                      onSelect={(slug) => {
                        selectNode(slug);
                        navigate("map");
                      }}
                    />
                  }
                  <div className="map-bottom">
                    <Legend />
                    <span className="subtle-label">{subjectTitle}</span>
                  </div>
                </section>
                <aside className="next-card">
                  <span className="next-icon">
                    <Sprout size={23} />
                  </span>
                  <p className="eyebrow">{t.next}</p>
                  <h2>{concept?.name_vi || t.topicTitle}</h2>
                  <p>
                    {config.mode === "mock" ? t.nextBody : t.flow.noLessonApi}
                  </p>
                  <span className="duration">
                    <Clock3 size={14} />
                    {config.mode === "mock" ? t.minutes : t.flow.api}
                  </span>
                  <Button
                    onClick={() =>
                      selected ? navigate("learn") : setTopicOpen(true)
                    }
                  >
                    {selected ? t.start : t.newTopic}
                    <ArrowRight size={16} />
                  </Button>
                  <button className="why-button" onClick={showTrace}>
                    <CircleHelp size={14} />
                    {t.why}
                  </button>
                </aside>
                <section className="sena-card">
                  <div className="sena-portrait">
                    <Sena size={118} />
                  </div>
                  <div>
                    <p className="eyebrow">{t.sena}</p>
                    <p className="sena-quote">“{t.senaQuote}”</p>
                  </div>
                  <Sparkles className="sena-spark" size={24} />
                </section>
                <section className="review-card">
                  <div className="review-icon">
                    <RotateCcw size={20} />
                  </div>
                  <div>
                    <h3>{t.reviewTitle}</h3>
                    <p>{t.reviewBody}</p>
                    <button
                      className="text-button"
                      onClick={() => navigate("reviews")}
                    >
                      {t.reviewCta}
                      <ArrowRight size={14} />
                    </button>
                  </div>
                </section>
              </div>
            </>
          )}

          {screen === "map" && (
            <>
              <PageHeading
                eyebrow={t.myPath}
                title={t.nav.map}
                description={t.prerequisite}
              />
              <div className="map-page-grid">
                <section className="panel large-map">
                  {
                    <MapContent
                      graph={graph}
                      selected={selected}
                      loading={busy.graph}
                      error={errors.graph}
                      onRetry={() => void learning.reloadGraph()}
                      onSelect={selectNode}
                    />
                  }
                  <div className="map-bottom">
                    <Legend />
                    <button
                      className="text-button"
                      onClick={() => void learning.reloadGraph()}
                      disabled={busy.graph}
                    >
                      {t.flow.reloadGraph}
                    </button>
                  </div>
                  <div className="concept-list" aria-label={t.flow.session}>
                    {graph.nodes.map((node) => (
                      <button
                        key={node.slug}
                        className={selected === node.slug ? "chosen" : ""}
                        aria-pressed={selected === node.slug}
                        onClick={() => selectNode(node.slug)}
                      >
                        {node.name_vi}
                      </button>
                    ))}
                  </div>
                </section>
                <aside className="panel concept-detail">
                  <p className="eyebrow">{t.selected}</p>
                  <span className="detail-icon">
                    <GitBranch size={25} />
                  </span>
                  {concept ? (
                    <>
                      <h2>{concept.name_vi || concept.slug}</h2>
                      <p>
                        {config.mode === "mock"
                          ? t.conceptDescriptions[conceptIndex]
                          : t.flow.noDescription}
                      </p>
                      <div className="mastery-row">
                        <span>{t.mastery}</span>
                        <strong>{Math.round(concept.p_known * 100)}%</strong>
                      </div>
                      <div className="progress-track">
                        <span style={{ width: `${concept.p_known * 100}%` }} />
                      </div>
                      {fixture && <SourceLink {...fixture.citation} />}
                      <Button onClick={() => navigate("learn")}>
                        {t.start}
                        <ArrowRight size={15} />
                      </Button>
                      <button className="why-button" onClick={showTrace}>
                        <CircleHelp size={14} />
                        {t.why}
                      </button>
                    </>
                  ) : (
                    <p>{t.flow.noNode}</p>
                  )}
                </aside>
              </div>
            </>
          )}

          {screen === "learn" && (
            <>
              <button
                className="text-button back-button"
                onClick={() => navigate("map")}
              >
                <ArrowLeft size={15} />
                {t.back}
              </button>
              <PageHeading
                eyebrow={t.lesson}
                title={fixture?.title || concept?.name_vi || t.flow.noLesson}
                description={
                  config.mode === "mock" ? t.flow.sampleContent : t.flow.api
                }
              />
              <div className="learning-grid">
                <section className="panel lesson-panel">
                  {fixture && (
                    <>
                      <div className="lesson-lead">
                        <span className="detail-icon">
                          <BookOpen size={22} />
                        </span>
                        <p>{fixture.body}</p>
                      </div>
                      <SourceLink {...fixture.citation} />
                    </>
                  )}
                  {busy[`lesson:${selected}`] && <Loading />}
                  <ErrorState
                    error={errors[`lesson:${selected}`]}
                    onRetry={() => void learning.loadLesson(selected, true)}
                  />
                  {!item && !busy[`lesson:${selected}`] && (
                    <div className="empty-inline">
                      <p>
                        {lesson?.done ? t.flow.placementDone : t.flow.noLesson}
                      </p>
                      {config.mode === "api" && <p>{t.flow.noLessonApi}</p>}
                      <Button
                        disabled={!selected || !learning.subject}
                        onClick={() => void learning.loadLesson(selected, true)}
                      >
                        {config.mode === "api"
                          ? t.flow.placement
                          : t.flow.retry}
                      </Button>
                    </div>
                  )}
                  {item && (
                    <div className="question">
                      <p className="eyebrow">{t.questionTitle}</p>
                      <h2>{item.prompt_vi}</h2>
                      <fieldset
                        disabled={!!result || busy[`attempt:${selected}`]}
                      >
                        <legend className="sr-only">{t.answerLabel}</legend>
                        {item.options.map((option, index) => (
                          <label
                            key={`${item.id}-${index}`}
                            className={`answer-option ${answer === index ? "is-selected" : ""}`}
                          >
                            <input
                              type="radio"
                              name={item.id}
                              value={index}
                              checked={answer === index}
                              onChange={() =>
                                learning.setAnswer(selected, index)
                              }
                            />
                            <span className="answer-letter">
                              {String.fromCharCode(65 + index)}
                            </span>
                            <code>{option.label}</code>
                            <span className="radio-indicator" />
                          </label>
                        ))}
                      </fieldset>
                      <div className="question-actions">
                        <Button
                          disabled={
                            answer === null ||
                            !!result ||
                            busy[`attempt:${selected}`] ||
                            (config.mode === "api" && !config.answerEncoding)
                          }
                          onClick={() => void learning.attempt()}
                        >
                          {busy[`attempt:${selected}`]
                            ? t.flow.saving
                            : t.check}
                          <CheckCheck size={17} />
                        </Button>
                        {result && (
                          <Button
                            variant="ghost"
                            onClick={() =>
                              config.mode === "api"
                                ? void learning.loadLesson(selected, true)
                                : learning.setAnswer(selected, null)
                            }
                          >
                            {t.retry}
                            <RotateCcw size={15} />
                          </Button>
                        )}
                        {config.mode === "api" && result && (
                          <Button
                            variant="secondary"
                            onClick={() =>
                              void learning.loadLesson(selected, true)
                            }
                          >
                            {t.flow.nextQuestion}
                          </Button>
                        )}
                      </div>
                      {config.mode === "api" && !config.answerEncoding && (
                        <p className="fine-print">
                          {t.flow.answerUnconfigured}
                        </p>
                      )}
                    </div>
                  )}
                  <ErrorState
                    error={errors[`attempt:${selected}`]}
                    onRetry={() => void learning.attempt()}
                  />
                  <div aria-live="polite">
                    {result && (
                      <div
                        className={`feedback ${result.correct ? "correct" : "incorrect"}`}
                      >
                        <strong>
                          {result.correct ? t.flow.correct : t.flow.incorrect}
                        </strong>
                        <p>
                          {result.correct
                            ? t.flow.correctBody
                            : result.misconception_vi || t.flow.incorrectBody}
                        </p>
                        {result.remediation && (
                          <>
                            <p>{result.remediation.reason_vi}</p>
                            <button
                              className="text-button"
                              onClick={() => {
                                selectNode(result.remediation!.concept_slug);
                                navigate("map");
                              }}
                            >
                              {t.flow.remediation}
                              <ArrowRight size={14} />
                            </button>
                          </>
                        )}
                        <button className="text-button" onClick={showTrace}>
                          {t.why}
                          <CircleHelp size={14} />
                        </button>
                      </div>
                    )}
                  </div>
                  <p className="fine-print draft-label">{t.draft}</p>
                </section>
                <aside className="panel tutor-panel">
                  <Sena size={105} />
                  <h2>{t.tutorTitle}</h2>
                  <p>{t.tutorSub}</p>
                  <div className="hint-list" aria-live="polite">
                    {lesson?.hints.map((hint, index) => (
                      <div className="hint-bubble" key={index}>
                        <span>
                          <Lightbulb size={14} />
                          {index + 1}
                        </span>
                        <p>{hint.hint_vi}</p>
                        {hint.citations.map((citation, i) => (
                          <SourceLink key={i} {...citation} />
                        ))}
                      </div>
                    ))}
                  </div>
                  <ErrorState
                    error={errors[`hint:${selected}`]}
                    onRetry={() => void learning.hint(tier)}
                  />
                  {busy[`hint:${selected}`] && (
                    <Loading label={t.flow.hintLoading} />
                  )}
                  {config.mode === "api" && config.hintFirstLevel === null ? (
                    <p className="fine-print">{t.flow.hintUnconfigured}</p>
                  ) : config.mode === "mock" && hintCount >= 2 ? (
                    <p className="hint-limit">{t.hintLimit}</p>
                  ) : (
                    <Button
                      variant="secondary"
                      disabled={!item || busy[`hint:${selected}`]}
                      onClick={() => void learning.hint(tier)}
                    >
                      <Lightbulb size={16} />
                      {t.hint}
                    </Button>
                  )}
                </aside>
              </div>
            </>
          )}

          {screen === "research" && (
            <section className="research-panel panel">
              <Sena size={140} />
              <p className="eyebrow">
                {submitted.mode === "deep" ? t.deep : t.quick}
              </p>
              <h1>
                {snapshot?.status === "ready"
                  ? t.flow.researchDone
                  : t.flow.researchTitle}
              </h1>
              <p>
                {config.mode === "mock" ? t.researchSub : t.flow.researchApi}
              </p>
              <div className="requested-goal">
                <small>{t.requested}</small>
                <strong>
                  {submitted.goal || submitted.fileName || t.flow.noData}
                </strong>
              </div>
              {busy.research && <Loading />}
              <p className="research-current" role="status">
                {snapshot?.step_vi}
              </p>
              {config.mode === "mock" && snapshot && (
                <div
                  className="research-progress"
                  role="progressbar"
                  aria-label={t.researchProgress}
                  aria-valuenow={snapshot.progress * 100}
                  aria-valuemin={0}
                  aria-valuemax={100}
                >
                  <span style={{ width: `${snapshot.progress * 100}%` }} />
                </div>
              )}
              <ErrorState
                error={errors.research}
                onRetry={learning.retryResearch}
              />
              <ol className="research-steps">
                {snapshot?.trail.map((event, index) => (
                  <li className="complete" key={`${event.at}-${index}`}>
                    <span>
                      <Check size={15} />
                    </span>
                    <div>
                      {event.text_vi}
                      {event.url && (
                        <SourceLink url={event.url} title={t.sourceAction} />
                      )}
                    </div>
                  </li>
                ))}
              </ol>
              {snapshot && !snapshot.trail.length && (
                <p className="empty-inline">{t.flow.researchEmpty}</p>
              )}
              {snapshot?.status === "failed" && (
                <Button
                  onClick={() => void startResearch()}
                  disabled={busy.create}
                >
                  {t.flow.researchRetry}
                </Button>
              )}
              <div className="research-sources">
                {sources.map((source, i) => (
                  <SourceLink key={i} url={source.url} title={source.title} />
                ))}
              </div>
              <p className="fine-print">
                {config.mode === "mock" ? t.flow.mockNotice : t.flow.apiNotice}
              </p>
              {snapshot?.status === "ready" && (
                <Button onClick={() => navigate("map")}>
                  {t.flow.researchOpen}
                  <ArrowRight size={16} />
                </Button>
              )}
              <button
                className="text-button"
                onClick={learning.retryResearch}
                disabled={busy.research}
              >
                {t.flow.refresh}
              </button>
              <button
                className="text-button"
                onClick={() => navigate("overview")}
              >
                {t.researchStop}
              </button>
            </section>
          )}

          {screen === "reviews" && (
            <>
              <PageHeading
                eyebrow={t.nav.reviews}
                title={t.reviewTitle}
                description={
                  config.mode === "mock" ? t.flow.reviewLocal : t.flow.reviewApi
                }
              />
              <section className="panel empty-panel">
                <span className="empty-icon">
                  <RotateCcw size={35} />
                </span>
                {busy.reviews && <Loading />}
                <ErrorState
                  error={errors.reviews}
                  onRetry={() => void learning.loadReviews()}
                />
                <h2>{reviewDue ? t.reviewReady : t.reviewEmpty}</h2>
                {learning.reviews.map((card) => (
                  <div className="review-entry" key={card.concept_slug}>
                    <strong>
                      {graph.nodes.find((n) => n.slug === card.concept_slug)
                        ?.name_vi || card.concept_slug}
                    </strong>
                    <span>{card.due_at}</span>
                    <Button
                      onClick={() => {
                        selectNode(card.concept_slug);
                        if (lessons[card.concept_slug])
                          learning.setAnswer(card.concept_slug, null);
                        navigate("learn");
                      }}
                    >
                      {t.reviewCta}
                      <ArrowRight size={16} />
                    </Button>
                  </div>
                ))}
                {!reviewDue && (
                  <>
                    <p>{t.reviewHint}</p>
                    <Button
                      disabled={!selected}
                      onClick={() => navigate("learn")}
                    >
                      {t.start}
                      <ArrowRight size={16} />
                    </Button>
                  </>
                )}
              </section>
            </>
          )}

          {screen === "sources" && (
            <>
              <PageHeading
                eyebrow={t.library}
                title={t.sourceTitle}
                description={config.mode === "mock" ? t.sourceSub : t.flow.api}
              />
              {sources.length ? (
                sources.map((source, i) => (
                  <section className="panel source-card" key={i}>
                    <span className="book-cover">
                      <BookOpen size={42} />
                    </span>
                    <div>
                      <span className="pill">
                        {source.license || t.flow.licenseUnknown}
                      </span>
                      <h2>{source.title || t.flow.sourceUnknown}</h2>
                      <p>{source.publisher}</p>
                      <SourceLink url={source.url} title={t.sourceAction} />
                    </div>
                  </section>
                ))
              ) : (
                <section className="panel empty-panel">
                  <Sena />
                  <p>{t.flow.sourcesEmpty}</p>
                </section>
              )}
              {config.mode === "mock" && (
                <p className="fine-print">{t.sourceNote}</p>
              )}
            </>
          )}
          {screen === "about" && (
            <section className="panel empty-panel">
              <Sena size={150} />
              <h1>{t.aboutTitle}</h1>
              <p>{t.flow.about}</p>
              <p className="pill">
                {config.mode === "mock" ? t.flow.demoTier : t.flow.apiTier}
              </p>
              <Button onClick={() => setTopicOpen(true)}>
                {t.newTopic}
                <Plus size={16} />
              </Button>
              {config.mode === "mock" && (
                <details className="demo-tools">
                  <summary>{t.flow.demoTools}</summary>
                  <p>{t.flow.demoToolsNote}</p>
                  <label htmlFor="demo-scenario">{t.flow.scenario}</label>
                  <select
                    id="demo-scenario"
                    value={scenario}
                    onChange={(event) =>
                      setScenario(event.target.value as DemoScenario)
                    }
                  >
                    <option value="normal">{t.flow.normal}</option>
                    <option value="fail-once">{t.flow.failOnce}</option>
                    <option value="empty">{t.flow.empty}</option>
                  </select>
                  <Button
                    variant="secondary"
                    onClick={() => learning.configureDemo(scenario)}
                  >
                    {t.flow.applyScenario}
                  </Button>
                </details>
              )}
            </section>
          )}
          <footer>
            <span>
              <Leaf size={13} />
              {t.footer}
            </span>
            <span>
              {t.app} <i>✳</i>
            </span>
          </footer>
        </main>
      </div>

      <Dialog.Root open={topicOpen} onOpenChange={setTopicOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-overlay" />
          <Dialog.Content className="dialog-content topic-dialog">
            <Dialog.Close className="dialog-close" aria-label={t.close}>
              <X size={20} />
            </Dialog.Close>
            <span className="detail-icon">
              <Sparkles size={24} />
            </span>
            <Dialog.Title>{t.topicTitle}</Dialog.Title>
            <Dialog.Description>{t.topicDescription}</Dialog.Description>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                void startResearch();
              }}
            >
              <label className="field-label" htmlFor="goal">
                {t.goal}
              </label>
              <textarea
                id="goal"
                placeholder={t.placeholder}
                value={goal}
                maxLength={500}
                aria-describedby="goal-count"
                disabled={busy.create}
                onChange={(event) => {
                  setGoal(event.target.value);
                  setFormError("");
                }}
              />
              <small
                id="goal-count"
                className="field-count"
                aria-label={t.flow.goalCount}
              >
                {goal.length}/500
              </small>
              <div className="suggestions">
                {t.suggested.map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    disabled={busy.create}
                    onClick={() => setGoal(suggestion)}
                  >
                    {suggestion}
                    <Plus size={12} />
                  </button>
                ))}
              </div>
              <span className="field-label">{t.mode}</span>
              <div className="mode-options" role="group" aria-label={t.mode}>
                <button
                  type="button"
                  disabled={busy.create}
                  className={mode === "quick" ? "selected-mode" : ""}
                  aria-pressed={mode === "quick"}
                  onClick={() => setMode("quick")}
                >
                  <Zap size={19} />
                  <strong>{t.quick}</strong>
                  <small>{t.quickDescription}</small>
                </button>
                <button
                  type="button"
                  disabled={busy.create}
                  className={mode === "deep" ? "selected-mode" : ""}
                  aria-pressed={mode === "deep"}
                  onClick={() =>
                    tier === "pro" ? setMode("deep") : setUpgradeOpen(true)
                  }
                >
                  <Sparkles size={19} />
                  <strong>{t.deep}</strong>
                  <small>{t.deepDescription}</small>
                </button>
              </div>
              {uploadEnabled ? (
                <>
                  <p className="demo-notice" id="upload-demo-notice">
                    {t.uploadDemoNotice}
                  </p>
                  <label className="upload-consent">
                    <input
                      type="checkbox"
                      checked={uploadConsent}
                      disabled={busy.upload || busy.create}
                      aria-describedby="upload-demo-notice"
                      onChange={(event) => {
                        setUploadConsent(event.target.checked);
                        if (!event.target.checked) {
                          setFile(null);
                          learning.clearUpload();
                          setFileError("");
                          if (fileRef.current) fileRef.current.value = "";
                        }
                      }}
                    />
                    <span>{t.uploadDemoConsent}</span>
                  </label>
                  <label
                    className={`upload-zone ${busy.upload ? "is-busy" : ""}`}
                  >
                    <Upload size={22} />
                    <strong>{file?.name ?? t.upload}</strong>
                    <small>
                      {config.mode === "mock"
                        ? t.uploadHint
                        : `${t.flow.uploadLimit}: ${config.uploadMaxBytes} ${t.flow.bytes}`}
                    </small>
                    <input
                      ref={fileRef}
                      className="sr-only"
                      type="file"
                      accept=".pdf,.docx"
                      disabled={!uploadConsent || busy.upload || busy.create}
                      onChange={(event) =>
                        void chooseFile(event.target.files?.[0])
                      }
                    />
                  </label>
                </>
              ) : (
                <p className="demo-notice">{t.flow.uploadDisabled}</p>
              )}
              {busy.upload && (
                <Loading
                  label={
                    config.mode === "mock"
                      ? t.flow.uploadingMock
                      : t.flow.uploading
                  }
                />
              )}
              {learning.upload && (
                <p className="upload-success" role="status">
                  {learning.upload.text_ok
                    ? config.mode === "mock"
                      ? t.flow.uploadLocal
                      : `${t.flow.uploaded} · ${learning.upload.pages} ${t.flow.pages}`
                    : t.flow.textUnreadable}
                </p>
              )}
              {file && (
                <button
                  disabled={busy.upload || busy.create}
                  className="text-button"
                  type="button"
                  onClick={() => {
                    setFile(null);
                    learning.clearUpload();
                    setFileError("");
                    if (fileRef.current) fileRef.current.value = "";
                  }}
                >
                  {t.removeFile}
                  <X size={14} />
                </button>
              )}
              {fileError && (
                <p className="error-text" role="alert">
                  {fileError}
                </p>
              )}
              <ErrorState
                error={errors.upload}
                onRetry={
                  file && !fileError && uploadConsent
                    ? () => void learning.uploadFile(file, uploadConsent)
                    : undefined
                }
              />
              <ErrorState
                error={errors.create}
                onRetry={() => void startResearch()}
              />
              {formError && (
                <p className="error-text" role="alert">
                  {formError}
                </p>
              )}
              <p className="demo-notice">
                <CircleHelp size={17} />
                {config.mode === "mock" ? t.flow.mockNotice : t.flow.apiNotice}
              </p>
              <p className="fine-print">{t.flow.newSession}</p>
              <div className="dialog-actions">
                <Button variant="ghost" onClick={() => setTopicOpen(false)}>
                  {t.cancel}
                </Button>
                <Button
                  type="submit"
                  disabled={
                    inFlight ||
                    (!goal.trim() && !learning.upload) ||
                    !!fileError ||
                    (!!file && !learning.upload) ||
                    (learning.upload !== null && !learning.upload.text_ok)
                  }
                >
                  {busy.create ? t.flow.loading : t.explore}
                  <ArrowRight size={16} />
                </Button>
              </div>
            </form>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      <Dialog.Root open={traceOpen} onOpenChange={setTraceOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-overlay" />
          <Dialog.Content className="dialog-content trace-dialog">
            <Dialog.Close className="dialog-close" aria-label={t.close}>
              <X size={20} />
            </Dialog.Close>
            <span className="detail-icon">
              <GitBranch size={24} />
            </span>
            <Dialog.Title>{t.traceTitle}</Dialog.Title>
            <Dialog.Description>{t.flow.traceIntro}</Dialog.Description>
            {busy[`lesson:${selected}`] && <Loading />}
            <ErrorState
              error={errors[`lesson:${selected}`]}
              onRetry={() => void learning.loadLesson(selected, true)}
            />
            {traces.length > 1 && (
              <label className="trace-picker">
                {t.flow.traceSelect}
                <select
                  value={traceIndex < 0 ? traces.length - 1 : traceIndex}
                  onChange={(event) =>
                    setTraceIndex(Number(event.target.value))
                  }
                >
                  {traces.map((entry, index) => (
                    <option value={index} key={index}>
                      {index + 1} · {entry.kind}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <TracePanel trace={trace} graph={graph} />
            <span className="pill">
              {config.mode === "mock" ? t.mock : t.flow.api}
            </span>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
      <Dialog.Root open={upgradeOpen} onOpenChange={setUpgradeOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-overlay" />
          <Dialog.Content className="dialog-content">
            <Dialog.Close className="dialog-close" aria-label={t.close}>
              <X size={20} />
            </Dialog.Close>
            <span className="detail-icon">
              <Sparkles size={24} />
            </span>
            <Dialog.Title>{t.pro}</Dialog.Title>
            <Dialog.Description>
              {config.mode === "mock" ? t.flow.upgrade : t.flow.liveUpgrade}
            </Dialog.Description>
            <p className="demo-notice">
              {config.mode === "mock" ? t.flow.demoTier : t.flow.apiTier}
            </p>
            <div className="dialog-actions">
              <Button variant="ghost" onClick={() => setUpgradeOpen(false)}>
                {t.close}
              </Button>
              <Button
                onClick={() => {
                  setTier("pro");
                  setUpgradeOpen(false);
                }}
              >
                {config.mode === "mock" ? t.flow.upgradeAction : t.pro}
              </Button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  );
}

function PageHeading({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <div className="page-heading">
      <p className="eyebrow">{eyebrow}</p>
      <h1>{title}</h1>
      <p>{description}</p>
    </div>
  );
}

function MapContent({
  graph,
  selected,
  loading,
  error,
  onRetry,
  onSelect,
}: {
  graph: KnowledgeGraph;
  selected: string;
  loading?: boolean;
  error: unknown;
  onRetry: () => void;
  onSelect: (slug: string) => void;
}) {
  if (loading) return <Loading />;
  if (error) return <ErrorState error={error} onRetry={onRetry} />;
  return <KnowledgeMap graph={graph} selected={selected} onSelect={onSelect} />;
}
