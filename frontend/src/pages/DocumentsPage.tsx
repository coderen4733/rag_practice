// 문서 관리 화면
//  - 문서 업로드(관리자급) + 등록 문서 목록/상세/삭제
//    1) 위쪽 단계 카드: ① 업로드 -> ② 텍스트 추출·청크 분할 -> ③ 임베딩 -> ④ Vector DB 저장
//       (업로드 진행 상태에 따라 색이 바뀜: 진행 중=빨강, 완료=초록, 실패=빨강 배경)
//    2) 업로드 카드: 파일을 끌어다 놓거나 선택해서 업로드 (.txt, .md)
//    3) 등록 문서 표: 상태/파일명 필터, 정렬, 페이지 번호, 상세 보기, 삭제
//  - 진행 상황은 오른쪽 AI Copilot 창에도 메시지로 표시됨

import { useCallback, useEffect, useRef, useState, type DragEvent, type FormEvent } from "react";
import { CircleCheck, CircleX, FileText, FileUp, RefreshCw, Search, Trash2, Upload } from "lucide-react";

import { ApiError } from "../api/client";
import { deleteDocument, getDocument, listDocuments, uploadDocument } from "../api/documents";
import type { DocumentItem, DocumentListQuery, DocumentStatus, PageResult } from "../api/types";
import { Badge } from "../components/ui/Badge";
import { Alert, EmptyState, Spinner } from "../components/ui/Feedback";
import { Modal } from "../components/ui/Modal";
import { Pagination } from "../components/ui/Pagination";
import { useAuth } from "../contexts/AuthContext";
import { useCopilot } from "../contexts/CopilotContext";
import { DOCUMENT_STATUS, formatBytes, formatDateTime, formatNumber } from "../utils/format";

// ───────────── 1. 단계 카드 설정 ─────────────
const STEPS = ["문서 파일 업로드", "텍스트 추출 · 청크 분할", "임베딩 생성", "Vector DB 저장"];

// 각 단계의 상태: idle(대기), active(진행 중), done(완료), error(실패)
type StepState = "idle" | "active" | "done" | "error";

const IDLE_STEPS: StepState[] = ["idle", "idle", "idle", "idle"];

// 업로드 실패 시 "몇 번째 단계"에서 실패했는지 추측 (백엔드 응답 코드와 메시지 기준)
//  - 413(너무 큼), 415(형식 오류) => ① 업로드 단계
//  - 400(인코딩 오류, 내용 없음)   => ② 텍스트 추출 단계
//  - 503 + "임베딩"               => ③ 임베딩 단계
//  - 503 그 외(Vector DB)          => ④ 저장 단계
function failedStepIndex(error: unknown): number {
  if (!(error instanceof ApiError)) return 0;
  if (error.status === 400) return 1;
  if (error.status === 503) return error.message.includes("임베딩") ? 2 : 3;
  return 0;
}

// 실패한 단계 기준으로 단계 상태 목록 만들기 (앞 단계는 완료, 실패 단계는 error, 뒤는 대기)
function stepsWithError(index: number): StepState[] {
  return STEPS.map((_, step) => (step < index ? "done" : step === index ? "error" : "idle"));
}

// 지원하는 확장자 (백엔드 parser.py의 SUPPORTED_EXTENSIONS와 같아야 함)
const ALLOWED_EXTENSIONS = [".txt", ".md"];

// 상태 필터 버튼 목록
const STATUS_FILTERS: { label: string; value?: DocumentStatus }[] = [
  { label: "전체" },
  { label: "처리 완료", value: "completed" },
  { label: "처리 실패", value: "failed" },
  { label: "처리 중", value: "processing" },
];

const errorMessage = (error: unknown) =>
  error instanceof ApiError ? error.message : "알 수 없는 오류가 발생했습니다.";

export function DocumentsPage() {
  const { isStaff } = useAuth();
  const { pushMessage, updateMessage } = useCopilot();

  // ───────────── 2. 업로드 상태 ─────────────
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false); // 파일을 끌고 영역 위에 올려놓은 상태
  const [uploading, setUploading] = useState(false);
  const [steps, setSteps] = useState<StepState[]>(IDLE_STEPS);
  const [uploadResult, setUploadResult] = useState<DocumentItem | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ───────────── 3. 목록 상태 ─────────────
  const [query, setQuery] = useState<DocumentListQuery>({ order: "desc", page: 1, size: 10 });
  const [filenameInput, setFilenameInput] = useState(""); // 검색창에 입력 중인 파일명
  const [result, setResult] = useState<PageResult<DocumentItem> | null>(null);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  // ───────────── 4. 팝업 상태 ─────────────
  const [detail, setDetail] = useState<DocumentItem | null>(null); // 상세 보기 중인 문서
  const [deleteTarget, setDeleteTarget] = useState<DocumentItem | null>(null); // 삭제 확인 중인 문서
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // 목록 불러오기 (query가 바뀔 때마다 다시 실행)
  const loadList = useCallback(async () => {
    setLoading(true);
    setListError(null);
    try {
      setResult(await listDocuments(query));
    } catch (error) {
      setListError(errorMessage(error));
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    loadList();
  }, [loadList]);

  // 조건 바꾸기 (조건이 바뀌면 1페이지부터 다시 보여줌)
  const updateQuery = (patch: Partial<DocumentListQuery>) =>
    setQuery((current) => ({ ...current, page: 1, ...patch }));

  // ───────────── 5. 파일 선택 ─────────────
  const selectFile = (selected: File | undefined) => {
    setUploadResult(null);
    setUploadError(null);
    setSteps(IDLE_STEPS);
    if (!selected) return;
    // 확장자 확인 (서버도 한 번 더 확인함)
    const extension = selected.name.slice(selected.name.lastIndexOf(".")).toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(extension)) {
      setFile(null);
      setUploadError(`지원하지 않는 파일 형식입니다. (${ALLOWED_EXTENSIONS.join(", ")} 만 가능)`);
      return;
    }
    setFile(selected);
  };

  // 파일을 끌어다 놓았을 때
  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault(); // 브라우저가 파일을 직접 열어버리는 기본 동작을 막음
    setDragging(false);
    selectFile(event.dataTransfer.files[0]);
  };

  // ───────────── 6. 업로드 ─────────────
  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setUploadError(null);
    setUploadResult(null);
    // 서버가 ①~④를 한 번에 처리하므로, 응답이 올 때까지 모든 단계를 "진행 중"으로 표시
    setSteps(["active", "active", "active", "active"]);
    const messageId = pushMessage({
      sender: "ai",
      tone: "loading",
      text: `${file.name} 파일을 업로드하고 임베딩하는 중입니다...`,
    });

    try {
      const document = await uploadDocument(file);
      setSteps(["done", "done", "done", "done"]);
      setUploadResult(document);
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = ""; // 같은 파일을 다시 선택할 수 있도록 초기화
      updateMessage(messageId, {
        tone: "success",
        text: `${document.filename} 문서 등록을 완료했습니다.`,
        details: [
          `텍스트 추출 · 청크 ${formatNumber(document.chunk_count)}개 생성`,
          "임베딩 생성 완료",
          "Vector DB 저장 완료",
        ],
        actions: [{ label: "문서 목록 보기", to: "/documents" }],
      });
      updateQuery({}); // 목록 새로고침 (1페이지로)
    } catch (error) {
      setSteps(stepsWithError(failedStepIndex(error)));
      setUploadError(errorMessage(error));
      updateMessage(messageId, { tone: "error", text: `${file.name} 등록 실패: ${errorMessage(error)}` });
      loadList(); // 실패한 문서도 목록에 "처리 실패"로 남으므로 새로고침
    } finally {
      setUploading(false);
    }
  };

  // ───────────── 7. 상세 보기 / 삭제 ─────────────
  const openDetail = async (document: DocumentItem) => {
    setDetail(document); // 먼저 목록의 정보로 바로 보여주고
    try {
      setDetail(await getDocument(document.id)); // 최신 정보로 다시 채움
    } catch {
      // 상세 조회 실패 시 목록의 정보를 그대로 보여줌
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteDocument(deleteTarget.id);
      pushMessage({
        sender: "ai",
        tone: "success",
        text: `${deleteTarget.filename} 문서를 삭제했습니다.`,
        details: ["DB 문서 정보 삭제", "Vector DB 청크 삭제"],
      });
      setDeleteTarget(null);
      setDetail(null);
      // 현재 페이지의 마지막 문서를 지웠으면 이전 페이지로 이동
      if (result && result.items.length === 1 && (query.page ?? 1) > 1) {
        setQuery((current) => ({ ...current, page: (current.page ?? 2) - 1 }));
      } else {
        loadList();
      }
    } catch (error) {
      setDeleteError(errorMessage(error));
    } finally {
      setDeleting(false);
    }
  };

  const handleSearch = (event: FormEvent) => {
    event.preventDefault();
    updateQuery({ filename: filenameInput.trim() || undefined });
  };

  return (
    <div className="page">
      <div className="page-header">
        <div className="page-title-row">
          <h1 className="page-title">문서 관리</h1>
          <p className="page-desc">
            문서를 업로드하면 텍스트 추출 → 청크 분할 → 임베딩 → Vector DB 저장까지 자동으로 진행합니다.
          </p>
        </div>
      </div>

      <div className="stack">
        {/* 1. 단계 카드 */}
        <div className="steps">
          {STEPS.map((label, index) => (
            <div key={label} className={`step ${steps[index] === "idle" ? "" : steps[index]}`}>
              <span className="step-number">{index + 1}</span>
              <span>{label}</span>
              <span className="step-state">
                {steps[index] === "active" && <Spinner size={16} />}
                {steps[index] === "done" && <CircleCheck size={18} color="var(--success)" />}
                {steps[index] === "error" && <CircleX size={18} color="var(--danger)" />}
              </span>
            </div>
          ))}
        </div>

        {/* 2. 업로드 카드 (관리자급만) */}
        {isStaff ? (
          <div className="card">
            <div className="card-header">
              <div className="card-title">
                <FileUp size={17} /> 문서 업로드
              </div>
              <button type="button" className="btn btn-primary" onClick={handleUpload} disabled={!file || uploading}>
                {uploading ? <Spinner size={15} /> : <Upload size={15} />}
                {uploading ? "처리 중..." : "업로드"}
              </button>
            </div>
            <div className="card-body form-stack">
              {/* 파일을 끌어다 놓거나 눌러서 선택하는 영역 */}
              <div
                className={`dropzone ${dragging ? "dragging" : ""}`}
                onClick={() => fileInputRef.current?.click()}
                onDragOver={(event) => {
                  event.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={handleDrop}
                role="button"
                tabIndex={0}
              >
                <FileUp size={28} />
                <strong>파일을 여기로 끌어다 놓거나 클릭해서 선택하세요</strong>
                <span style={{ fontSize: 12 }}>지원 형식: .txt, .md · 기본 최대 1MB (서버 설정에 따라 다름)</span>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept={ALLOWED_EXTENSIONS.join(",")}
                  hidden
                  onChange={(event) => selectFile(event.target.files?.[0])}
                />
              </div>

              {file && (
                <div className="selected-file">
                  <FileText size={18} />
                  <strong style={{ flex: 1 }}>{file.name}</strong>
                  <span className="muted">{formatBytes(file.size)}</span>
                </div>
              )}
              {uploading && (
                <Alert tone="info">서버에서 청크 분할과 임베딩을 진행하고 있습니다. 문서 크기에 따라 시간이 걸릴 수 있어요.</Alert>
              )}
              {uploadError && <Alert tone="error">{uploadError}</Alert>}
              {uploadResult && (
                <Alert tone="success">
                  {uploadResult.filename} 등록 완료 · 청크 {formatNumber(uploadResult.chunk_count)}개가 Vector DB에 저장되었습니다.
                </Alert>
              )}
            </div>
          </div>
        ) : (
          <Alert tone="info">문서 등록과 삭제는 관리자·매니저 권한이 필요합니다. 등록된 문서 목록은 누구나 볼 수 있어요.</Alert>
        )}

        {/* 3. 등록 문서 목록 */}
        <div className="card">
          <div className="card-header">
            <div className="card-title">
              등록 문서 <span className="count-pill">{result ? formatNumber(result.total) : "-"}</span>
            </div>
            <button type="button" className="btn btn-outline btn-sm" onClick={loadList} disabled={loading}>
              {loading ? <Spinner size={14} /> : <RefreshCw size={14} />} 새로고침
            </button>
          </div>

          {/* 필터 */}
          <div className="filters">
            <div className="segmented">
              {STATUS_FILTERS.map((filter) => (
                <button
                  key={filter.label}
                  type="button"
                  className={query.status === filter.value ? "active" : ""}
                  onClick={() => updateQuery({ status: filter.value })}
                >
                  {filter.label}
                </button>
              ))}
            </div>
            <form onSubmit={handleSearch} style={{ display: "flex", gap: 6 }}>
              <input
                className="input"
                value={filenameInput}
                onChange={(event) => setFilenameInput(event.target.value)}
                placeholder="파일명 검색"
                aria-label="파일명 검색"
              />
              <button type="submit" className="btn btn-outline">
                <Search size={15} /> 검색
              </button>
            </form>
            <select
              className="select"
              value={query.order}
              onChange={(event) => updateQuery({ order: event.target.value as "asc" | "desc" })}
              aria-label="정렬"
            >
              <option value="desc">최신 등록순</option>
              <option value="asc">오래된 순</option>
            </select>
          </div>

          {listError && (
            <div className="card-body">
              <Alert tone="error">{listError}</Alert>
            </div>
          )}

          {result && result.items.length > 0 ? (
            <>
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th className="center">No</th>
                      <th>파일명</th>
                      <th className="center">형식</th>
                      <th className="right">크기</th>
                      <th className="right">청크 수</th>
                      <th className="center">상태</th>
                      <th>등록일</th>
                      <th className="right">작업</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.items.map((document) => (
                      <tr key={document.id} className="clickable" onClick={() => openDetail(document)}>
                        <td className="center muted">{document.id}</td>
                        <td style={{ fontWeight: 600 }}>{document.filename}</td>
                        <td className="center">{document.file_extension}</td>
                        <td className="right">{formatBytes(document.file_size)}</td>
                        <td className="right">{formatNumber(document.chunk_count)}</td>
                        <td className="center">
                          <Badge tone={DOCUMENT_STATUS[document.status].tone}>{DOCUMENT_STATUS[document.status].label}</Badge>
                        </td>
                        <td className="muted">{formatDateTime(document.created_at)}</td>
                        <td>
                          {/* stopPropagation: 버튼을 누를 때 행 클릭(상세 보기)이 함께 실행되지 않도록 */}
                          <div className="cell-actions" onClick={(event) => event.stopPropagation()}>
                            <button type="button" className="btn btn-outline btn-sm" onClick={() => openDetail(document)}>
                              상세
                            </button>
                            {isStaff && (
                              <button type="button" className="btn btn-danger-outline btn-sm" onClick={() => setDeleteTarget(document)}>
                                <Trash2 size={13} /> 삭제
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination
                page={result.page}
                totalPages={result.total_pages}
                total={result.total}
                onChange={(page) => setQuery((current) => ({ ...current, page }))}
              />
            </>
          ) : (
            !listError && (
              <EmptyState
                icon={loading ? <Spinner size={22} /> : <FileText size={26} />}
                title={loading ? "불러오는 중..." : "조건에 맞는 문서가 없습니다."}
              />
            )
          )}
        </div>
      </div>

      {/* 상세 보기 팝업 */}
      {detail && (
        <Modal
          title="문서 상세"
          onClose={() => setDetail(null)}
          width={560}
          footer={
            <>
              {isStaff && (
                <button type="button" className="btn btn-danger-outline" onClick={() => setDeleteTarget(detail)}>
                  <Trash2 size={14} /> 삭제
                </button>
              )}
              <button type="button" className="btn btn-dark" onClick={() => setDetail(null)}>
                닫기
              </button>
            </>
          }
        >
          <dl className="detail-list">
            <dt>문서 ID</dt>
            <dd>{detail.id}</dd>
            <dt>파일명</dt>
            <dd>{detail.filename}</dd>
            <dt>형식 / 크기</dt>
            <dd>
              {detail.file_extension} · {formatBytes(detail.file_size)} ({formatNumber(detail.file_size)} bytes)
            </dd>
            <dt>상태</dt>
            <dd>
              <Badge tone={DOCUMENT_STATUS[detail.status].tone}>{DOCUMENT_STATUS[detail.status].label}</Badge>
            </dd>
            <dt>청크 수</dt>
            <dd>{formatNumber(detail.chunk_count)}개</dd>
            <dt>실패 이유</dt>
            <dd className={detail.error_message ? "text-danger" : "muted"}>{detail.error_message ?? "-"}</dd>
            <dt>등록자 ID</dt>
            <dd>{detail.uploaded_by ?? "(삭제된 사용자)"}</dd>
            <dt>등록일</dt>
            <dd>{formatDateTime(detail.created_at)}</dd>
            <dt>수정일</dt>
            <dd>{formatDateTime(detail.updated_at)}</dd>
          </dl>
        </Modal>
      )}

      {/* 삭제 확인 팝업 */}
      {deleteTarget && (
        <Modal
          title="문서 삭제"
          onClose={() => {
            setDeleteTarget(null);
            setDeleteError(null);
          }}
          footer={
            <>
              <button type="button" className="btn btn-outline" onClick={() => setDeleteTarget(null)} disabled={deleting}>
                취소
              </button>
              <button type="button" className="btn btn-danger" onClick={handleDelete} disabled={deleting}>
                {deleting ? <Spinner size={14} /> : <Trash2 size={14} />} 삭제
              </button>
            </>
          }
        >
          <div className="form-stack">
            <p>
              <strong>{deleteTarget.filename}</strong> 문서를 삭제할까요?
            </p>
            <Alert tone="warning">
              DB의 문서 정보와 Vector DB에 저장된 청크 {formatNumber(deleteTarget.chunk_count)}개가 함께 삭제되며 되돌릴 수 없습니다.
            </Alert>
            {deleteError && <Alert tone="error">{deleteError}</Alert>}
          </div>
        </Modal>
      )}
    </div>
  );
}
