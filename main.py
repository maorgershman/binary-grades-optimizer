from dataclasses import dataclass
from argparse import ArgumentParser
import sys
from pathlib import Path
from tabulate import tabulate

from transcript import Course, Err, PercentageGrade, Transcript, parse_transcript_file

# Return the percentage-graded courses, sorted from most harmful to most beneficial for GPA.
@dataclass(frozen=True)
class CourseGpaImpact:
    course: Course
    gpa_impact: float

def calculate_courses_sorted_by_deviation_from_gpa(transcript: Transcript) -> list[CourseGpaImpact]:
    def calculate_gpa(transcript: Transcript) -> float:
        weighted_sum = sum(
            c.credits * c.grade.score
            for c in transcript.courses
            if isinstance(c.grade, PercentageGrade)
        )
        relevant_credits = sum(
            c.credits
            for c in transcript.courses
            if isinstance(c.grade, PercentageGrade)
        )
        if relevant_credits == 0:
            raise ValueError("Transcript has no percentage-graded courses")
        return weighted_sum / relevant_credits
    
    gpa = calculate_gpa(transcript)
    return [
        CourseGpaImpact(course=course, gpa_impact=impact)
        for course, impact
        in sorted(
            [
                (c, (c.grade.score - gpa) * c.credits)
                for c in transcript.courses
                if isinstance(c.grade, PercentageGrade)
            ],
            key=lambda x: x[1],
        )
    ]

def main(transcript_file_path: Path):
    transcript_result = parse_transcript_file(transcript_file_path)
    if isinstance(transcript_result, Err):
        print(transcript_result.error, file=sys.stderr)
        raise SystemExit(1)

    transcript = transcript_result.value
    courses = calculate_courses_sorted_by_deviation_from_gpa(transcript)
    print("\n\n"
          "These are the courses that you can use a binary passing grade for, "
          "sorted how much they hurt your GPA. "
          "Earlier in the list means hurts your GPA more. "
          "If possible, apply binary passing grades to the earliest courses in this list. "
          "\n\n")

    print(tabulate(
        [
            [
                course.course.id,
                course.course.name,
                course.course.credits,
                course.course.grade.score,
                course.course.semester,
            ]
            for course in courses
        ],
        headers=["ID", "Name", "Credits", "Grade", "Semester"],
        tablefmt="rounded_outline",
    ))

if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("transcript_file_path", type=Path)
    args = parser.parse_args()
    main(transcript_file_path=args.transcript_file_path)
