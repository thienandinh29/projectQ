"""Research runner; search backend injection keeps vendor selection with the team."""

import asyncio
import math
import posixpath
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from time import monotonic
from typing import TYPE_CHECKING
from urllib.parse import quote, unquote, urlsplit, urlunsplit

if TYPE_CHECKING:
    from app.research.relevance import ResearchRelevance

from app.research.reader import (
    Allowlist,
    Publisher,
    SafeReader,
    SourceError,
    load_allowlist,
    validate_url,
)
from app.uploads.reader import Document, Page, read_link


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str = ""


@dataclass(frozen=True)
class ChosenSource:
    title: str
    publisher: str
    url: str
    license: str
    text: str
    license_source_url: str | None = None
    pages: tuple[Page, ...] = ()
    retrieval_query: str = ""
    license_text: str = ""


Search = Callable[[str, Sequence[str]], Awaitable[Sequence[SearchResult]]]
OnEvent = Callable[[dict[str, str]], Awaitable[None]]


def detect_license(text: str) -> str:
    """Accept explicit CC grants found in the document, never search-result metadata."""
    normalized = text.casefold()
    if re.search(r"shared under (?:a )?not declared license", normalized):
        raise SourceError(
            "Chưa có giấy phép được công bố cho trang tài liệu này.", code="license_missing"
        )
    if re.search(
        r"may not.{0,180}(?:ingested into large language models|training of large language models)",
        " ".join(normalized.split()),
    ):
        raise SourceError(
            "Nguồn yêu cầu chấp thuận riêng trước khi dùng với mô hình AI.",
            code="ai_permission_required",
        )
    if re.search(
        r"\bby(?:[-\s]+nc)?[-\s]+nd\b|creativecommons.org/licenses/by[^\s]*nd|"
        r"attribution[-\s]+(?:noncommercial[-\s]+)?no[-\s]+derivative(?:s|[-\s]+works)?\b",
        normalized,
    ):
        raise SourceError("Không sử dụng tài liệu có giấy phép ND.", code="license_nd")
    for code in ("by-nc-sa", "by-nc", "by-sa", "by"):
        found = re.search(
            rf"(?:creativecommons\.org/licenses/{code}/|\bcc[ -]+{code}[ /]+)([1-4]\.0|2\.5)",
            normalized,
        )
        if found:
            return f"CC {code.upper()} {found[1]}"
    for name, code in (
        ("attribution-noncommercial-sharealike", "BY-NC-SA"),
        ("attribution-noncommercial", "BY-NC"),
        ("attribution-sharealike", "BY-SA"),
        ("attribution", "BY"),
    ):
        found = re.search(rf"creative commons {name}\s+([1-4]\.0|2\.5)\b", normalized)
        if found:
            return f"CC {code} {found[1]}"
    if "creativecommons.org/publicdomain/zero/1.0" in normalized or "cc0 1.0" in normalized:
        return "CC0 1.0"
    raise SourceError("Chưa xác định được giấy phép mở của tài liệu.", code="license_missing")


def canonical_url(url: str) -> str:
    parsed = urlsplit(url)
    host = parsed.netloc.lower()
    if host.endswith(":443"):
        host = host[:-4]
    return urlunsplit(
        (
            parsed.scheme,
            host,
            quote(normalized_path(parsed.path).rstrip("/"), safe="/:@"),
            parsed.query,
            "",
        )
    )


def normalized_path(path: str) -> str:
    for _ in range(3):
        decoded = unquote(path)
        if decoded == path:
            break
        path = decoded
    return posixpath.normpath(path)


class ResearchAgent:
    def __init__(
        self,
        search: Search,
        *,
        allowlist: Allowlist | None = None,
        reader: SafeReader | None = None,
        max_searches: int = 15,
        max_reads: int = 12,
        deadline_seconds: float = 480,
        relevance: "ResearchRelevance | None" = None,
        open_web: bool = False,
    ) -> None:
        if not (1 <= max_searches <= 15 and 1 <= max_reads <= 12 and 0 < deadline_seconds <= 480):
            raise ValueError("Research limits exceed the contract")
        self.allowlist = allowlist or load_allowlist()
        if open_web:
            self.allowlist = self.allowlist.model_copy(update={"allow_public": True})
        if reader is not None and reader.allowlist != self.allowlist:
            raise ValueError("Research reader must enforce the same allowlist")
        self.reader = reader or SafeReader(allowlist=self.allowlist)
        self.search = search
        self.relevance = relevance
        self.open_web = open_web
        self.max_searches, self.max_reads, self.deadline = max_searches, max_reads, deadline_seconds

    async def research(self, goal: str, on_event: OnEvent) -> list[ChosenSource]:
        if not goal.strip() or len(goal) > 2000:
            raise SourceError("Mục tiêu học tập rỗng hoặc quá dài.")
        publisher_count = sum(not p.fallback_only for p in self.allowlist.publishers)
        per_publisher_reads = max(1, math.ceil(self.max_reads / max(1, publisher_count)))
        seen: set[str] = set()
        selected_urls: set[str] = set()
        linked_licenses: dict[str, tuple[str, str]] = {}
        followup_urls: set[str] = set()
        pending_documents: dict[str, Document] = {}
        deferred: dict[str, SearchResult] = {}
        sources: list[ChosenSource] = []
        publishers: set[str] = set()
        searches = reads = 0
        completed_searches = 0
        rejected: dict[str, int] = {}
        publisher_selections: dict[str, int] = {}
        started = monotonic()

        async def event(kind: str, text: str, url: str = "", **details: str) -> None:
            await on_event(
                {
                    "kind": kind,
                    "text_vi": text,
                    "url": url,
                    "elapsed_seconds": f"{monotonic() - started:.1f}",
                    **details,
                }
            )

        try:
            async with asyncio.timeout(self.deadline):
                search_goal = goal.strip()
                alternate_query = ""
                topic_query = ""
                if self.relevance is not None:
                    plan = await self.relevance.plan(goal)
                    search_goal = plan.query
                    alternate_query = plan.alternate_query
                    topic_query = plan.topic_query
                    await event("search", "Phạm vi tìm tài liệu: " + plan.scope_vi)
                scopes: list[Publisher | None] = [
                    p for p in self.allowlist.publishers if not p.fallback_only
                ]
                if self.open_web:
                    domains = list(dict.fromkeys(d for p in scopes if p for d in p.domains))
                    preferred = (
                        [Publisher(name="các nguồn ưu tiên", domains=domains)] if domains else []
                    )
                    scopes = [None, *preferred, None]
                for scope_index, publisher in enumerate(scopes):
                    if searches >= self.max_searches or reads >= self.max_reads:
                        continue
                    searches += 1
                    domains = publisher.domains if publisher else []
                    label = publisher.name if publisher else "web mở rộng (ngoài danh sách ưu tiên)"
                    # Adapters receive the domain scope separately. Do not turn site:
                    # operators into stray query words when sanitizing model queries.
                    query = (
                        search_goal
                        if self.relevance
                        else (
                            f"{search_goal} open textbook"
                            if not publisher
                            else f"{search_goal} textbook site:{publisher.domains[0]}"
                        )
                    )
                    if self.relevance and domains == ["ocw.mit.edu"]:
                        query = f"{topic_query or search_goal} chapter textbook resource"
                    if publisher is None:
                        query = f"{search_goal} chapter lesson Creative Commons"
                        if scope_index:
                            query = f"{topic_query or search_goal} introductory textbook chapter "
                            query += "open educational resources"
                    await event("search", f"Đang tìm giáo trình tại {label}…")
                    try:
                        results = await self.search(query, domains)
                        completed_searches += 1
                        count = len(results)
                        if self.relevance:
                            if (
                                alternate_query
                                and alternate_query != query
                                and searches < self.max_searches
                            ):
                                searches += 1
                                variant = (
                                    f"{alternate_query} chapter lesson Creative Commons"
                                    if publisher is None
                                    else alternate_query
                                )
                                if publisher is None and scope_index:
                                    variant = f"{topic_query or alternate_query} tutorial section "
                                    variant += "open textbook Creative Commons"
                                alternatives = await self.search(variant, domains)
                                results = list(results) + list(alternatives)
                                count = len(results)
                            results = await self.relevance.rank(goal, results)
                            # Prefer individual HTML lessons over whole-book downloads.
                            results = sorted(
                                results,
                                key=lambda r: (
                                    0
                                    if "/resources/" in r.url or "/chapter/" in r.url
                                    else 1
                                    if "/pages/open-textbook" in r.url
                                    else 2,
                                    urlsplit(r.url).path.lower().endswith(".pdf")
                                    or "/open/download" in r.url,
                                ),
                            )
                        await event(
                            "search",
                            f"Truy vấn: {query}. Có {count} kết quả, "
                            f"{len(results)} ứng viên bài học sau xếp hạng.",
                        )
                        if not results:
                            code = "no_relevant_candidates" if count else "search_no_results"
                            rejected[code] = rejected.get(code, 0) + 1
                            await event(
                                "search",
                                "Không có ứng viên bài học phù hợp trong lượt tìm này.",
                                code=code,
                                outcome="rejected",
                                stage="search",
                            )
                    except SourceError as exc:
                        rejected[exc.code] = rejected.get(exc.code, 0) + 1
                        await event(
                            "search", str(exc), code=exc.code, outcome="rejected", stage="search"
                        )
                        if exc.retryable:
                            continue
                        raise
                    publisher_reads = publisher_selected = 0
                    read_limit = (
                        max(1, self.max_reads // 3)
                        if publisher is None
                        else max(1, self.max_reads // 3)
                        if self.open_web
                        else max(3, per_publisher_reads)
                        if self.relevance
                        else per_publisher_reads
                    )
                    results = list(results)
                    for result in results:
                        key = canonical_url(result.url)
                        cached = pending_documents.get(key) if key in linked_licenses else None
                        if (
                            (reads >= self.max_reads and cached is None)
                            or (
                                publisher_reads >= read_limit
                                and canonical_url(result.url) not in linked_licenses
                                and key not in followup_urls
                            )
                            or (
                                not self.open_web
                                and publisher is not None
                                and publisher_selected >= 2
                            )
                        ):
                            break
                        if key in seen:
                            continue
                        try:
                            self.allowlist.publisher(result.url)
                        except SourceError:
                            continue
                        owner = ".".join(validate_url(result.url).split(".")[-2:])
                        if publisher_selections.get(owner, 0) >= 2:
                            continue
                        if (
                            self.open_web
                            and len(publishers) == 1
                            and publisher_selections.get(owner, 0)
                        ):
                            deferred[key] = result
                            continue
                        seen.add(key)
                        if cached is None:
                            reads += 1
                            publisher_reads += 1
                        await event("read", f"Đang đọc {result.title}…", result.url)
                        document = None
                        text = ""
                        try:
                            document = cached or await read_link(
                                result.url, self.reader, pdf_page_limit=40
                            )
                            actual = self.allowlist.publisher(document.source_uri)
                            final_url = canonical_url(document.source_uri)
                            if final_url in selected_urls:
                                continue
                            if not document.text_ok:
                                rejected["unreadable_document"] = (
                                    rejected.get("unreadable_document", 0) + 1
                                )
                                await event(
                                    "read",
                                    "Tài liệu không có văn bản bài học đọc được.",
                                    result.url,
                                    code="unreadable_document",
                                    outcome="rejected",
                                    stage="reading",
                                )
                                continue
                            text = "\n".join(p.text for p in document.pages)
                            license_text = document.license_text or text
                            if document.total_pages and document.total_pages > len(document.pages):
                                await event(
                                    "read",
                                    f"PDF có {document.total_pages} trang; "
                                    f"chỉ đọc trang 1-{len(document.pages)} cho bài học đầu. "
                                    "Các phần còn lại chưa được dùng.",
                                    document.source_uri,
                                    code="document_sampled",
                                    stage="reading",
                                )
                            if document.chapter_links:
                                detect_license(license_text)
                                chapters = [
                                    SearchResult(title, url)
                                    for title, url in document.chapter_links
                                ]
                                if self.relevance:
                                    chapters = await self.relevance.rank(goal, chapters)
                                for chapter in reversed(chapters):
                                    followup_urls.add(canonical_url(chapter.url))
                                    results.insert(results.index(result) + 1, chapter)
                                await event(
                                    "read",
                                    "Đang chọn chương từ mục lục giáo trình.",
                                    document.source_uri,
                                )
                                continue
                            if document.resource_links:
                                detect_license(license_text)
                                for link in reversed(document.resource_links[:1]):
                                    linked_licenses[canonical_url(link)] = (
                                        license_text,
                                        document.source_uri,
                                    )
                                    if canonical_url(link) in pending_documents:
                                        seen.discard(canonical_url(link))
                                    results.insert(
                                        results.index(result) + 1, SearchResult(result.title, link)
                                    )
                                await event(
                                    "read",
                                    "Đang mở PDF được trang tài nguyên công bố.",
                                    document.source_uri,
                                )
                                continue
                            grant = linked_licenses.get(final_url)
                            if grant and "all rights reserved" in text.casefold():
                                # Do not let a page-wide grant override restrictions in the file.
                                license_name = detect_license(text)
                            else:
                                license_name = detect_license(
                                    license_text + ("\n" + grant[0] if grant else "")
                                )
                            if cached is not None:
                                pending_documents.pop(key, None)
                                rejected["license_missing"] = max(
                                    0, rejected.get("license_missing", 0) - 1
                                )
                                await event(
                                    "read",
                                    "Đã xác minh giấy phép qua trang tài nguyên liên kết đúng PDF; "
                                    "tái dùng bản đã tải.",
                                    document.source_uri,
                                    code="license_verified",
                                    stage="licensing",
                                )
                        except SourceError as exc:
                            if (
                                document is not None
                                and document.media_type == "application/pdf"
                                and exc.code == "license_missing"
                                and "all rights reserved" not in text.casefold()
                            ):
                                pending_documents[key] = document
                            rejected[exc.code] = rejected.get(exc.code, 0) + 1
                            await event(
                                "read",
                                "Bỏ qua nguồn: " + str(exc),
                                result.url,
                                code=exc.code,
                                outcome="rejected",
                                stage="reading",
                            )
                            if (
                                not self.open_web
                                and publisher is not None
                                and exc.code == "ai_permission_required"
                            ):
                                break
                            continue
                        candidate = ChosenSource(
                            result.title,
                            actual.name,
                            document.source_uri,
                            license_name,
                            text,
                            license_source_url=grant[1] if grant else None,
                            pages=document.pages
                            if document.media_type == "application/pdf"
                            else (),
                            retrieval_query=search_goal if self.relevance else "",
                            license_text=license_text + ("\n" + grant[0] if grant else ""),
                        )
                        if self.relevance is not None and not await self.relevance.supports(
                            goal, candidate
                        ):
                            rejected["not_instructional"] = rejected.get("not_instructional", 0) + 1
                            await event(
                                "read",
                                "Nguồn chưa được xác nhận có bài học phù hợp: " + result.title,
                                document.source_uri,
                                code="not_instructional",
                                outcome="rejected",
                                stage="relevance",
                            )
                            continue
                        sources.append(candidate)
                        selected_urls.add(final_url)
                        publisher_selected += 1
                        owner = ".".join(validate_url(document.source_uri).split(".")[-2:])
                        publisher_selections[owner] = publisher_selections.get(owner, 0) + 1
                        publishers.add(owner)
                        if len(publishers) >= 2 and deferred:
                            results.extend(deferred.values())
                            followup_urls.update(deferred)
                            deferred.clear()
                        await event(
                            "select",
                            f"Đã chọn {result.title} ({license_name}).",
                            document.source_uri,
                        )
                        if len(sources) >= 3 and len(publishers) >= 2:
                            return sources
        except TimeoutError:
            raise SourceError(
                "Nghiên cứu đã hết thời gian; hãy xem các nguồn bị loại trong báo cáo.",
                code="research_timeout",
                action_vi="Kiểm tra nguồn chậm/lỗi tải; thu hẹp mục tiêu "
                "hoặc cung cấp tài liệu hợp lệ.",
            ) from None
        if not completed_searches:
            raise SourceError(
                "Dịch vụ tìm kiếm không hoàn tất được lượt tìm nào; chưa thể đánh giá tài liệu.",
                code="research_search_unavailable",
                action_vi="Kiểm tra cấu hình, hạn mức search và các mã lỗi HTTP trong báo cáo.",
            )
        raise SourceError(
            f"Chưa đủ nguồn: chọn được {len(sources)}/3 tài liệu "
            f"từ {len(publishers)}/2 nhà xuất bản "
            f"sau {searches} lượt tìm và {reads} lượt đọc. "
            + "Lý do loại: "
            + (
                ", ".join(f"{code}: {count}" for code, count in sorted(rejected.items()))
                or "không có kết quả tìm kiếm phù hợp"
            )
            + ".",
            code="research_sources_insufficient",
            action_vi="Xem từng nguồn bị loại bên dưới. Cần bài học đúng chủ đề "
            "và giấy phép cho phép sử dụng; có thể cung cấp tài liệu được phép dùng.",
        )


async def research(goal: str, on_event: OnEvent) -> list[ChosenSource]:
    """Public entry point requires a job-local backend, configured by the worker."""
    from app.research.runtime import current_agent

    return await current_agent().research(goal, on_event)
