import json
from pathlib import Path

from .models import InvestigationTrace, TraceEvent


class JsonlTraceStorage:
    """Persist trace events as newline-delimited JSON."""

    def write(
        self,
        path: str | Path,
        events: list[TraceEvent],
    ) -> None:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("w", encoding="utf-8") as file:
            for event in events:
                file.write(
                    json.dumps(
                        event.model_dump(mode="json"),
                        sort_keys=True,
                    )
                    + "\n"
                )

    def read(
        self,
        path: str | Path,
    ) -> list[TraceEvent]:
        input_path = Path(path)

        with input_path.open("r", encoding="utf-8") as file:
            return [
                TraceEvent.model_validate_json(line) for line in file if line.strip()
            ]

    def write_investigation(
        self,
        path: str | Path,
        trace: InvestigationTrace,
    ) -> None:
        """Persist a complete investigation trace as JSON."""
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        output_path.write_text(
            trace.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def read_investigation(
        self,
        path: str | Path,
    ) -> InvestigationTrace:
        """Read a complete investigation trace from JSON."""
        input_path = Path(path)

        return InvestigationTrace.model_validate_json(
            input_path.read_text(encoding="utf-8")
        )
