import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import NewType, cast

from returns.iterables import Fold
from returns.result import Success, Failure, Result
import pdfplumber

CourseId = NewType("CourseId", str)
CourseName = NewType("CourseName", str)
CourseCredits = NewType("CourseCredits", float)
Semester = NewType("Semester", str)

@dataclass(frozen=True)
class PercentageGrade:
    score: int

    def __post_init__(self) -> None:
        if not (0 <= self.score <= 100):
            raise ValueError("Grade must be between 0 and 100")

class SpecialGrade(StrEnum):
    PASSED = "passed"
    EXEMPTION_WITH_POINTS = "exemption_with_points"
    EXEMPTION_WITHOUT_POINTS = "exemption_without_points"

type CourseGrade = PercentageGrade | SpecialGrade

@dataclass(frozen=True)
class Course:
    id: CourseId
    name: CourseName
    credits: CourseCredits
    grade: CourseGrade
    semester: Semester

@dataclass(frozen=True)
class Transcript:
    courses: list[Course]

@dataclass(frozen=True, slots=True)
class TranscriptError:
    message: str

type DirtyPage = str
type TranscriptFilePath = Path

def _extract_dirty_pages(path: TranscriptFilePath) -> Result[list[DirtyPage], TranscriptError]:
    try:
        with pdfplumber.open(path) as pdf:
            return Success([page.extract_text() for page in pdf.pages])
    except Exception as error:
        return Failure(TranscriptError(f"Could not open transcript PDF: {error}"))

def _maybe_drop_trailing_page(pages: list[DirtyPage]) -> Result[list[DirtyPage], TranscriptError]:
    if len(pages) == 3:
        return Success(pages[:-1])
    return Success(pages)

type CleanPage = str

def _clean_pages(pages: list[DirtyPage]) -> Result[list[CleanPage], TranscriptError]:
    def process_page(page: DirtyPage) -> Result[CleanPage, TranscriptError]:
        start_after = "SUBJECT CREDITS GRADE SEMESTER\n"
        
        start_idx = page.find(start_after)
        if start_idx == -1:
            return Failure(TranscriptError("Could not find transcript table header"))
        end_idx = page.rfind("\nEND OF TRANSCRIPT")
        if end_idx == -1:
            end_idx = page.rfind("\n(E): The course was taught in English")
        if end_idx == -1:
            return Failure(TranscriptError("Could not find transcript table footer"))
        
        return Success(page[start_idx + len(start_after) : end_idx])
    
    cleaned_pages: list[CleanPage] = []
    for page_number, page in enumerate(pages, start=1):
        result = process_page(page).alt(lambda error, page_number=page_number: TranscriptError(f"Page {page_number}: {error}"))
        if isinstance(result, Failure):
            return result
        cleaned_pages.append(result.unwrap())
    return Success(cleaned_pages)

type Line = str

def _extract_lines(pages: list[CleanPage]) -> Result[list[Line], TranscriptError]:
    lines = "\n".join(pages).split("\n")
    
    # Fix courses with long names that spill on multiple lines
    fixed_lines: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not bool(re.match(r'^\d{8}', line)):
            if i + 2 >= len(lines):
                return Failure(TranscriptError(f"Could not repair wrapped course line: {line!r}"))
            l1 = line
            l2 = lines[i + 1]
            l3 = lines[i + 2]
            fixed_lines.append(f"{l2[:8]} {l1} {l3} {l2[9:]}")
            i += 3
        else:
            fixed_lines.append(line)
            i += 1
    return Success(fixed_lines)

def _extract_id(line: Line) -> tuple[CourseId, Line]:
    return CourseId(line[:8]), line[9:]

def _extract_semester(line: Line) -> Result[tuple[Semester, Line], TranscriptError]:
    sem_match = re.search(r'(\d{4}-\d{4}\s+(?:Winter|Spring|Summer))$', line, re.IGNORECASE)
    if sem_match is None:
        return Failure(TranscriptError(f"Could not parse semester from line: {line!r}"))
    
    sem_str = sem_match.group(1)
    line = line[:sem_match.start()].strip() # Pop semester off the string
    
    return Success((Semester(sem_str), line))

def _extract_grade(line: Line) -> Result[tuple[CourseGrade, Line], TranscriptError]:
    delim = " 0 Exemption without points"
    idx = line.rfind(delim)
    if idx != -1:
        line = line[:idx] + " 0"
        return Success((SpecialGrade.EXEMPTION_WITHOUT_POINTS, line))
    
    delim = " Exemption without points"
    idx = line.rfind(delim)
    if idx != -1:
        line = line[:idx] + " 0"
        return Success((SpecialGrade.EXEMPTION_WITHOUT_POINTS, line))
    
    delim = " Exemption with points"
    idx = line.rfind(delim)
    if idx != -1:
        line = line[:idx]
        return Success((SpecialGrade.EXEMPTION_WITH_POINTS, line))
    
    delim = " Exemption"
    idx = line.rfind(delim)
    if idx != -1:
        line = line[:idx]
        return Success((SpecialGrade.EXEMPTION_WITH_POINTS, line))
    
    delim = " Pass"
    idx = line.rfind(delim)
    if idx != -1:
        line = line[:idx]
        return Success((SpecialGrade.PASSED, line))
    
    score_match = re.search(r'(100|[1-9]?\d)$', line)
    if score_match is None:
        return Failure(TranscriptError(f"Could not parse course grade from line: {line!r}"))
    
    score_str = score_match.group(1)
    line = line[:score_match.start()].strip() # Pop score off the string
    
    return Success((PercentageGrade(int(score_str)), line))

def _extract_credits(line: Line) -> Result[tuple[CourseCredits, Line], TranscriptError]:
    line = line.strip()
    if line == "SEXUAL HARASSMENT PREVENTION":
        return Success((CourseCredits(0), line))

    idx = line.rfind(" ")
    if idx == -1:
        return Failure(TranscriptError(f"Could not parse credits from line: {line!r}"))
    return Success((CourseCredits(float(line[idx + 1:])), line[:idx]))

def _parse_courses(lines: list[Line]) -> Result[list[Course], TranscriptError]:
    def _parse_course(line: Line) -> Result[Course, TranscriptError]:
        id, line = _extract_id(line)
        return Result.do(
            Course(
                id=id,
                name=CourseName(name),
                credits=credits,
                grade=grade,
                semester=semester,
            )
            for semester, line in _extract_semester(line)
            for grade, line in _extract_grade(line)
            for credits, name in _extract_credits(line)
        )
    
    # Cast due to a bug in Pylance.
    # This is the correct type, and this is not a code smell.
    return cast(
        Result[tuple[Course, ...], TranscriptError],
        Fold.collect(map(_parse_course, lines), Success(()))
    ).map(list)

def parse_transcript_file(path: TranscriptFilePath) -> Result[Transcript, TranscriptError]:
    return (
        _extract_dirty_pages(path)
        .bind(_maybe_drop_trailing_page)
        .bind(_clean_pages)
        .bind(_extract_lines)
        .bind(_parse_courses)
        .map(Transcript)
    )
