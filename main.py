from argparse import ArgumentParser
from tabulate import tabulate

from transcript import *

# Return [c_1, ..., c_n] where: 
# c_1, ..., c_n don't already have a binary passing grade.
# c_1 is the most harmful course for the gpa.
# c_n is the most beneficial course for the gpa.
def calculate_courses_sorted_by_deviation_from_gpa(transcript: Transcript) -> list[Course]:
    def calculate_gpa(transcript: Transcript) -> float:
        weighted_sum = sum([c.credits * c.grade.score for c in transcript.courses if isinstance(c.grade, PercentageGrade)])
        relevant_credits = sum([c.credits for c in transcript.courses if isinstance(c.grade, PercentageGrade)])
        return weighted_sum / relevant_credits
    
    gpa = calculate_gpa(transcript)
    return [
        course for course, _ 
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
    transcript = parse_transcript_file(transcript_file_path)
    courses = calculate_courses_sorted_by_deviation_from_gpa(transcript)
    print("\n\n"
          "These are the courses that you can use a binary passing grade for, "
          "sorted how much they hurt your GPA. "
          "Earlier in the list means hurts your GPA more. "
          "If possible, apply binary passing grades to the earliest courses in this list. "
          "\n\n")

    print(tabulate(
        [
            [c.id, c.name, c.credits, c.grade.score, c.semester] # type: ignore
            for c in courses
        ],
        headers=["ID", "Name", "Credits", "Grade", "Semester"],
        tablefmt="rounded_outline",
    ))

if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("transcript_file_path", type=Path)
    args = parser.parse_args()
    main(transcript_file_path=args.transcript_file_path)
