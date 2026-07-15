import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import NewType

import pdfplumber

Semester = NewType("Semester", str)
CourseId = NewType("CourseId", str)
CourseName = NewType("CourseName", str)
CourseCredits = NewType("CourseCredits", float)

@dataclass(frozen=True)
class PercentageGrade:
    score: int

class SpecialGrade(StrEnum):
    PASSED = "passed"
    EXEMPTION_WITH_POINTS = "exemption_with_points"
    EXEMPTION_WITHOUT_POINTS = "exemption_without_points"

CourseGrade = PercentageGrade | SpecialGrade

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
    
def _extract_dirty_pages(transcript_file_path: Path) -> list[str]:
    with pdfplumber.open(transcript_file_path) as pdf:
        return [page.extract_text() for page in pdf.pages]

def _clean_pages(dirty_pages: list[str]) -> list[str]:
    def process_page(page: str) -> str:
        start_after = "SUBJECT CREDITS GRADE SEMESTER\n"
        
        start_idx = page.find(start_after)
        end_idx = page.rfind("\nEND OF TRANSCRIPT")
        if end_idx == -1:
            end_idx = page.rfind("\n(E): The course was taught in English")
        
        return page[start_idx + len(start_after) : end_idx]
        
    return [process_page(page) for page in dirty_pages]

def _extract_lines(clean_pages: list[str]) -> list[str]:
    lines = "\n".join(clean_pages).split("\n")
    
    # Fix courses with long names that spill on multiple lines
    fixed_lines: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not bool(re.match(r'^\d{8}', line)):
            l1 = line
            l2 = lines[i + 1]
            l3 = lines[i + 2]
            fixed_lines.append(f"{l2[:8]} {l1} {l3} {l2[9:]}")
            i += 3
        else:
            fixed_lines.append(line)
            i += 1
    return fixed_lines

def _extract_id(line: str) -> tuple[CourseId, str]:
    return CourseId(line[:8]), line[9:]

def _extract_semester(line: str) -> tuple[Semester, str]:
    sem_match = re.search(r'(\d{4}-\d{4}\s+(?:Winter|Spring|Summer))$', line, re.IGNORECASE)
    assert sem_match is not None
    
    sem_str = sem_match.group(1)
    line = line[:sem_match.start()].strip() # Pop semester off the string
    
    return Semester(sem_str), line

def _extract_grade(line: str) -> tuple[CourseGrade, str]:
    delim = " 0 Exemption without points"
    idx = line.rfind(delim)
    if idx != -1:
        line = line[:idx] + " 0"
        return SpecialGrade.EXEMPTION_WITHOUT_POINTS, line
    
    delim = " Exemption without points"
    idx = line.rfind(delim)
    if idx != -1:
        line = line[:idx] + " 0"
        return SpecialGrade.EXEMPTION_WITHOUT_POINTS, line
    
    delim = " Exemption with points"
    idx = line.rfind(delim)
    if idx != -1:
        line = line[:idx]
        return SpecialGrade.EXEMPTION_WITH_POINTS, line
    
    delim = " Exemption"
    idx = line.rfind(delim)
    if idx != -1:
        line = line[:idx]
        return SpecialGrade.EXEMPTION_WITH_POINTS, line
    
    delim = " Pass"
    idx = line.rfind(delim)
    if idx != -1:
        line = line[:idx]
        return SpecialGrade.PASSED, line
    
    score_match = re.search(r'(100|[1-9]?\d)$', line)
    assert score_match is not None
    
    score_str = score_match.group(1)
    line = line[:score_match.start()].strip() # Pop score off the string
    
    return PercentageGrade(int(score_str)), line

def _extract_credits(line: str) -> tuple[CourseCredits, str]:
    idx = line.rfind(" ")
    return CourseCredits(float(line[idx + 1:])), line[:idx]

def _parse_courses(lines: list[str]) -> list[Course]:
    def parse_course(line: str) -> Course:
        id, line = _extract_id(line)
        semester, line = _extract_semester(line)
        grade, line = _extract_grade(line)
        
        if line == "SEXUAL HARASSMENT PREVENTION":
            line += " 0"
        
        credits, line = _extract_credits(line)
        name = CourseName(line)
        return Course(
            id=id,
            name=name,
            credits=credits,
            grade=grade,
            semester=semester,
        )
    
    return [parse_course(line) for line in lines]

def parse_transcript_file(transcript_file_path: Path) -> Transcript:
    dirty_pages = _extract_dirty_pages(transcript_file_path)
    if len(dirty_pages) == 3:
        dirty_pages.pop()
    
    clean_pages = _clean_pages(dirty_pages)
    lines = _extract_lines(clean_pages)
    courses = _parse_courses(lines)
    return Transcript(courses)
