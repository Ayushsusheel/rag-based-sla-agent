import shutil
import subprocess
from pathlib import Path

from app.config import LIBREOFFICE_CANDIDATES
from app.logging_config import logger, log_step


def find_soffice() -> Path | None:
    for p in LIBREOFFICE_CANDIDATES:
        if p.exists():
            return p

    which = shutil.which("soffice")
    if which:
        return Path(which)

    return None


def convert_docx_to_pdf(docx_path: Path, out_dir: Path) -> Path:
    soffice = find_soffice()
    if not soffice:
        raise RuntimeError(
            "LibreOffice 'soffice' not found. Please install LibreOffice locally for DOCX support."
        )

    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(soffice),
        "--headless",
        "--convert-to",
        "pdf:writer_pdf_Export",
        "--outdir",
        str(out_dir),
        str(docx_path),
    ]

    with log_step("convert_docx_to_pdf", file=docx_path.name):
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"DOCX to PDF conversion failed.\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            )

        expected = out_dir / f"{docx_path.stem}.pdf"
        if expected.exists():
            logger.info(f"[bold yellow]DOCX canonicalized[/] pdf={expected.name}")
            return expected

        matches = list(out_dir.glob(f"{docx_path.stem}*.pdf"))
        if matches:
            logger.info(f"[bold yellow]DOCX canonicalized[/] pdf={matches[0].name}")
            return matches[0]

        raise RuntimeError("DOCX conversion completed but output PDF was not found.")