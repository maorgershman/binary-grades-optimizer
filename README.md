# Binary Grades Optimizer

Prints the percentage-graded courses whose conversion to binary pass/fail would
help GPA the most, based on a transcript PDF.

## Usage

Requires Python 3.11 or newer.

```sh
python3 -m venv .venv
```

PowerShell:

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m main <transcript.pdf>
```

Bash:

```bash
source .venv/Scripts/activate
python -m pip install -r requirements.txt
python -m main <transcript.pdf>
```

The transcript PDF must be a valid Technion transcript.
