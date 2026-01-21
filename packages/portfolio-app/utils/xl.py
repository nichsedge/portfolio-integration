import sys
from pathlib import Path
import pandas as pd


def safe_name(name: str) -> str:
    return "".join(c if c.isalnum() or c in (" ", "_", "-") else "_" for c in name).strip()


def infer_engine(ext: str) -> str | None:
    ext = ext.lower()
    if ext == ".xls":
        # xlrd 2.x removed xls support; pandas may still try to use it but will fail.
        # We intentionally request xlrd engine for legacy .xls.
        return "xlrd"
    if ext == ".xlsx":
        return "openpyxl"
    return None


def read_excel_any(path: Path):
    engine = infer_engine(path.suffix)
    # Try reading all sheets, falling back progressively.
    # 1) Excel via pandas
    try:
        return pd.read_excel(path, sheet_name=None, engine=engine)
    except Exception as e_excel:
        # 2) If file is actually CSV but misnamed .xls/.xlsx
        for enc in ("utf-8-sig", "utf-8", "cp1252", "latin1"):
            try:
                df = pd.read_csv(path, encoding=enc)
                return {"Sheet1": df}
            except Exception:
                continue
        # Re-raise original excel error if CSV heuristics fail
        raise e_excel


def main():
    # Default input: "Money Manager.xls" unless provided via argv
    in_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("Money Manager.xls")

    if not in_path.exists():
        raise FileNotFoundError(f"Input file not found: {in_path}")

    book = read_excel_any(in_path)

    # If only one sheet, write a single CSV named after the input file (without extension)
    if isinstance(book, dict) and len(book) == 1:
        sheet_name, df = next(iter(book.items()))
        out_csv = in_path.with_suffix(".csv")
        df.to_csv(out_csv, index=False)
        return

    # Otherwise, write one CSV per sheet with safe names
    base = in_path.stem
    for name, df in book.items():
        out_csv = Path(f"{base}__{safe_name(name)}.csv")
        df.to_csv(out_csv, index=False)


if __name__ == "__main__":
    main()