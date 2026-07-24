import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Callable, Generic, NewType, TypeVar, Never

import pdfplumber

CourseId = NewType("CourseId", str)
CourseName = NewType("CourseName", str)
CourseCredits = NewType("CourseCredits", float)
Semester = NewType("Semester", str)

@dataclass(frozen=True)
class PercentageGrade:
    score: int

    def __post_init__(self):
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

################
# Result monad #
################

T = TypeVar("T", covariant=True)
U = TypeVar("U", covariant=True)

E = TypeVar("E", covariant=True)
F = TypeVar("F", covariant=True)

@dataclass(frozen=True, slots=True)
class Ok(Generic[T]):
    value: T

    def map(self, f: Callable[[T], U]) -> Result[U, Never]:
        return Ok(f(self.value))

    def bind(self, f: Callable[[T], Result[U, E]]) -> Result[U, E]:
        return f(self.value)

    def map_err(self, _: Callable[[Never], F]) -> Result[T, F]:
        return self

    def unwrap(self) -> T:
        return self.value

    def unwrap_err(self) -> Never:
        raise RuntimeError("Called unwrap_err() on Ok")

@dataclass(frozen=True, slots=True)
class Err(Generic[E]):
    error: E

    def map(self, _: Callable[[Never], U]) -> Result[U, E]:
        return self

    def bind(self, _: Callable[[Never], Result[U, F]]) -> Result[U, E]:
        return self

    def map_err(self, f: Callable[[E], F]) -> Result[Never, F]:
        return Err(f(self.error))

    def unwrap(self) -> Never:
        raise RuntimeError(f"Called unwrap() on Err: {self.error!r}")

    def unwrap_err(self) -> E:
        return self.error

type Result[T, E] = Ok[T] | Err[E]

###################

@dataclass(frozen=True, slots=True)
class TranscriptError:
    message: str

type DirtyPage = str
type TranscriptFilePath = Path

def _extract_dirty_pages(path: TranscriptFilePath) -> Result[list[DirtyPage], TranscriptError]:
    try:
        with pdfplumber.open(path) as pdf:
            return Ok([page.extract_text() for page in pdf.pages])
    except Exception as error:
        return Err(TranscriptError(f"Could not open transcript PDF: {error}"))

def _maybe_drop_trailing_page(pages: list[DirtyPage]) -> Result[list[DirtyPage], TranscriptError]:
    if len(pages) == 3:
        return Ok(pages[:-1])
    return Ok(pages)

type CleanPage = str

def _clean_pages(pages: list[DirtyPage]) -> Result[list[CleanPage], TranscriptError]:
    def process_page(page: DirtyPage) -> Result[CleanPage, TranscriptError]:
        start_after = "SUBJECT CREDITS GRADE SEMESTER\n"
        
        start_idx = page.find(start_after)
        if start_idx == -1:
            return Err(TranscriptError("Could not find transcript table header"))
        end_idx = page.rfind("\nEND OF TRANSCRIPT")
        if end_idx == -1:
            end_idx = page.rfind("\n(E): The course was taught in English")
        if end_idx == -1:
            return Err(TranscriptError("Could not find transcript table footer"))
        
        return Ok(page[start_idx + len(start_after) : end_idx])
    
    cleaned_pages: list[CleanPage] = []
    for page_number, page in enumerate(pages, start=1):
        result = process_page(page).map_err(lambda error, page_number=page_number: TranscriptError(f"Page {page_number}: {error}"))
        if isinstance(result, Err):
            return result
        cleaned_pages.append(result.value)
    return Ok(cleaned_pages)

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
                return Err(TranscriptError(f"Could not repair wrapped course line: {line!r}"))
            l1 = line
            l2 = lines[i + 1]
            l3 = lines[i + 2]
            fixed_lines.append(f"{l2[:8]} {l1} {l3} {l2[9:]}")
            i += 3
        else:
            fixed_lines.append(line)
            i += 1
    return Ok(fixed_lines)

def _extract_id(line: Line) -> tuple[CourseId, Line]:
    return CourseId(line[:8]), line[9:]

def _extract_semester(line: Line) -> Result[tuple[Semester, Line], TranscriptError]:
    sem_match = re.search(r'(\d{4}-\d{4}\s+(?:Winter|Spring|Summer))$', line, re.IGNORECASE)
    if sem_match is None:
        return Err(TranscriptError(f"Could not parse semester from line: {line!r}"))
    
    sem_str = sem_match.group(1)
    line = line[:sem_match.start()].strip() # Pop semester off the string
    
    return Ok((Semester(sem_str), line))

def _extract_grade(line: Line) -> Result[tuple[CourseGrade, Line], TranscriptError]:
    delim = " 0 Exemption without points"
    idx = line.rfind(delim)
    if idx != -1:
        line = line[:idx] + " 0"
        return Ok((SpecialGrade.EXEMPTION_WITHOUT_POINTS, line))
    
    delim = " Exemption without points"
    idx = line.rfind(delim)
    if idx != -1:
        line = line[:idx] + " 0"
        return Ok((SpecialGrade.EXEMPTION_WITHOUT_POINTS, line))
    
    delim = " Exemption with points"
    idx = line.rfind(delim)
    if idx != -1:
        line = line[:idx]
        return Ok((SpecialGrade.EXEMPTION_WITH_POINTS, line))
    
    delim = " Exemption"
    idx = line.rfind(delim)
    if idx != -1:
        line = line[:idx]
        return Ok((SpecialGrade.EXEMPTION_WITH_POINTS, line))
    
    delim = " Pass"
    idx = line.rfind(delim)
    if idx != -1:
        line = line[:idx]
        return Ok((SpecialGrade.PASSED, line))
    
    score_match = re.search(r'(100|[1-9]?\d)$', line)
    if score_match is None:
        return Err(TranscriptError(f"Could not parse course grade from line: {line!r}"))
    
    score_str = score_match.group(1)
    line = line[:score_match.start()].strip() # Pop score off the string
    
    return Ok((PercentageGrade(int(score_str)), line))

def _extract_credits(line: Line) -> Result[tuple[CourseCredits, Line], TranscriptError]:
    line = line.strip()
    if line == "SEXUAL HARASSMENT PREVENTION":
        return Ok((CourseCredits(0), line))

    idx = line.rfind(" ")
    if idx == -1:
        return Err(TranscriptError(f"Could not parse credits from line: {line!r}"))
    return Ok((CourseCredits(float(line[idx + 1:])), line[:idx]))

def _parse_course(line: Line) -> Result[Course, TranscriptError]:
    course_id, remainder = _extract_id(line)
    return (
        Ok(remainder)
        .bind(_extract_semester)
        .bind(
            lambda parsed_semester: _extract_grade(parsed_semester[1]).bind(
                lambda parsed_grade: _extract_credits(parsed_grade[1]).map(
                    lambda parsed_credits: Course(
                        id=course_id,
                        name=CourseName(parsed_credits[1]),
                        credits=parsed_credits[0],
                        grade=parsed_grade[0],
                        semester=parsed_semester[0],
                    )
                )
            )
        )
    )

def _parse_courses(lines: list[Line]) -> Result[list[Course], TranscriptError]:
    courses: list[Course] = []
    for line in lines:
        course_result = _parse_course(line)
        if isinstance(course_result, Err):
            return course_result
        courses.append(course_result.value)
    return Ok(courses)

def parse_transcript_file(path: TranscriptFilePath) -> Result[Transcript, TranscriptError]:
    return (
        _extract_dirty_pages(path)
        .bind(_maybe_drop_trailing_page)
        .bind(_clean_pages)
        .bind(_extract_lines)
        .bind(_parse_courses)
        .map(Transcript)
    )
