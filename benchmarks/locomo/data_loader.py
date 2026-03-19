"""Parse locomo10.json into Pydantic models."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from pydantic import BaseModel

logger = logging.getLogger(__name__)

_LOCOMO_URL = (
    "https://raw.githubusercontent.com/snap-research/locomo/main/data/locomo10.json"
)


def _ensure_dataset(data_file: Path) -> None:
    """
    Download locomo10.json if it doesn't already exist locally.

    Args:
        data_file (Path): Expected path to the dataset file

    Raises:
        RuntimeError: If the download fails
    """
    if data_file.exists():
        return

    logger.info("Downloading LoCoMo dataset to %s …", data_file)
    data_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        with urlopen(_LOCOMO_URL) as resp:  # noqa: S310
            data_file.write_bytes(resp.read())
    except (URLError, OSError) as exc:
        data_file.unlink(missing_ok=True)  # clean up partial file
        raise RuntimeError(
            f"Failed to download LoCoMo dataset from {_LOCOMO_URL}: {exc}"
        ) from exc

    logger.info("Download complete (%d bytes).", data_file.stat().st_size)


class LoCoMoTurn(BaseModel):
    """A single conversation turn."""

    speaker: str
    dia_id: str
    text: str


class LoCoMoSession(BaseModel):
    """One conversation session with a timestamp."""

    session_id: int
    date_time: str
    turns: list[LoCoMoTurn]


class LoCoMoQA(BaseModel):
    """A QA annotation."""

    question: str
    answer: str  # coerced from int/float in loader
    category: int  # 1-5
    evidence: list[str]


class LoCoMoSample(BaseModel):
    """A full LoCoMo conversation sample with sessions and QA pairs."""

    sample_id: int
    speaker_a: str
    speaker_b: str
    sessions: list[LoCoMoSession]
    qa: list[LoCoMoQA]


def load_locomo(data_file: str | Path) -> list[LoCoMoSample]:
    """
    Load and parse locomo10.json.

    Args:
        data_file (str | Path): Path to locomo10.json

    Returns:
        list[LoCoMoSample]: Parsed samples
    """
    data_file = Path(data_file)
    _ensure_dataset(data_file)

    with data_file.open() as f:
        raw = json.load(f)

    samples: list[LoCoMoSample] = []
    for idx, item in enumerate(raw):
        conv = item["conversation"]
        speaker_a = conv.get("speaker_a", "Speaker A")
        speaker_b = conv.get("speaker_b", "Speaker B")

        # Parse sessions: keys like "session_1", "session_2", ...
        sessions: list[LoCoMoSession] = []
        session_num = 1
        while True:
            session_key = f"session_{session_num}"
            if session_key not in conv:
                break
            turns_raw = conv[session_key]
            date_time = conv.get(f"{session_key}_date_time", "")
            turns = [
                LoCoMoTurn(
                    speaker=t["speaker"],
                    dia_id=t["dia_id"],
                    text=t["text"],
                )
                for t in turns_raw
            ]
            sessions.append(
                LoCoMoSession(
                    session_id=session_num,
                    date_time=date_time,
                    turns=turns,
                )
            )
            session_num += 1

        # Parse QA
        qa_list = [
            LoCoMoQA(
                question=str(q["question"]),
                answer=str(q.get("answer", q.get("adversarial_answer", ""))),
                category=q["category"],
                evidence=q.get("evidence", []),
            )
            for q in item.get("qa", [])
        ]

        samples.append(
            LoCoMoSample(
                sample_id=idx,
                speaker_a=speaker_a,
                speaker_b=speaker_b,
                sessions=sessions,
                qa=qa_list,
            )
        )

    return samples
